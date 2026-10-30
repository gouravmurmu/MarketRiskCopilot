"""Daily commentary workflow: gather, draft, validate, retry, store.

    python -m riskcopilot.agent.daily [--as-of YYYY-MM-DD] [--force]

1. Gather: code calls every tool in a fixed order, so the input is identical every run.
2. Draft: Claude returns structured JSON (see draft.Draft).
3. Validate: every number must match a tool output; warnings and breaches must be reported.
4. Retry: validator errors go back to the model, up to `agent_max_retries` times, after which
   the draft is stored as "needs_review".
5. The analyst edits and approves it in the UI. Approved commentary is never overwritten
   unless --force is given.
"""

import argparse
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from riskcopilot.agent import llm
from riskcopilot.agent.draft import Draft, output_schema, render_markdown
from riskcopilot.agent.tools import DAILY_GATHER, call_tool, dumps
from riskcopilot.agent.validator import validate
from riskcopilot.api.deps import resolve_as_of
from riskcopilot.config import Settings, get_settings
from riskcopilot.db import models as m
from riskcopilot.db import repo

log = logging.getLogger(__name__)


@dataclass
class DailyResult:
    as_of: date
    status: str  # draft | needs_review | skipped
    attempts: int = 0
    errors: list[str] = field(default_factory=list)
    trace_id: str | None = None


def gather(session: Session, as_of: date, tracer: llm.Tracer | None = None) -> dict[str, Any]:
    """Tool outputs keyed by tool name, plus its arguments when a tool is called twice."""
    names = [n for n, _ in DAILY_GATHER]
    out: dict[str, Any] = {}
    for name, args in DAILY_GATHER:
        full = {"as_of": as_of.isoformat(), **args}
        key = name if names.count(name) == 1 else f"{name}({json.dumps(args, sort_keys=True)})"
        t0 = time.perf_counter()
        ok, result = call_tool(session, name, full)
        out[key] = result if ok else {"error": result}
        if tracer:
            tracer.log(tool=name, args=full, output=dumps(out[key]), started=t0)
    return out


def _user_prompt(as_of: date, outputs: dict[str, Any]) -> str:
    return (
        f"Business date: {as_of.isoformat()}.\n"
        f"<tool_outputs>\n{json.dumps(outputs, indent=1, default=str)}\n</tool_outputs>\n"
        "Write today's risk commentary as JSON."
    )


def draft_commentary(
    session: Session,
    as_of: date,
    client: Any,
    settings: Settings,
    tracer: llm.Tracer,
) -> tuple[Draft | None, DailyResult, dict[str, Any]]:
    outputs = gather(session, as_of, tracer)
    messages: list[dict[str, Any]] = [{"role": "user", "content": _user_prompt(as_of, outputs)}]
    result = DailyResult(as_of, "needs_review", trace_id=tracer.trace_id)
    draft: Draft | None = None
    for attempt in range(settings.agent_max_retries + 1):
        result.attempts = attempt + 1
        t0 = time.perf_counter()
        resp = client.beta.messages.create(
            **llm.request_kwargs(settings),
            max_tokens=16000,
            system=llm.DAILY_SYSTEM,
            messages=messages,
            output_config={
                "effort": settings.agent_effort,
                "format": {"type": "json_schema", "schema": output_schema()},
            },
        )
        text = llm.text_of(resp)
        tracer.log(
            output=text,
            tokens=llm.usage_tokens(resp),
            started=t0,
            model=getattr(resp, "model", settings.agent_model),
        )
        if resp.stop_reason == "refusal":
            result.errors = ["The model declined to write this commentary"]
            break
        if resp.stop_reason == "max_tokens":
            errors = ["The response was cut off; keep the commentary shorter"]
        else:
            try:
                draft = Draft.model_validate_json(text)
            except ValidationError as e:
                draft, errors = None, [f"Output did not match the schema: {e}"]
            else:
                report = validate(draft, outputs)
                errors = report.errors
        result.errors = errors
        if not errors:
            result.status = "draft"
            break
        messages += [
            {"role": "assistant", "content": resp.content},
            {
                "role": "user",
                "content": "The validator rejected the draft:\n- "
                + "\n- ".join(errors)
                + "\nFix these using only figures from the tool outputs and return the full JSON.",
            },
        ]
    return draft, result, outputs


def run_daily(
    session_factory: sessionmaker[Session],
    as_of: date | None = None,
    client: Any = None,
    settings: Settings | None = None,
    force: bool = False,
) -> DailyResult:
    settings = settings or get_settings()
    with session_factory.begin() as session:
        as_of = resolve_as_of(session, as_of)
        existing = session.get(m.Commentary, as_of)
        if existing is not None and existing.status == "approved" and not force:
            return DailyResult(as_of, "skipped", errors=["Already approved"])
        client = client or llm.make_client(settings)
        tracer = llm.Tracer(session, "daily", as_of)
        draft, result, _ = draft_commentary(session, as_of, client, settings, tracer)
        repo.upsert(
            session,
            m.Commentary,
            [
                {
                    "as_of": as_of,
                    "draft_md": render_markdown(draft, as_of.isoformat()) if draft else None,
                    "final_md": None,
                    "status": result.status,
                    "validator_report": {
                        "ok": result.status == "draft",
                        "attempts": result.attempts,
                        "errors": result.errors,
                        "model": settings.agent_model,
                        "trace_id": result.trace_id,
                        "draft": draft.model_dump() if draft else None,
                    },
                    "approved_by": None,
                    "approved_at": None,
                }
            ],
        )
    log.info("commentary %s: %s after %d attempt(s)", as_of, result.status, result.attempts)
    return result


def main() -> None:
    from riskcopilot.db.session import make_engine, make_session_factory

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    parser.add_argument("--force", action="store_true", help="Redraft approved commentary")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set")
    factory = make_session_factory(make_engine(settings.database_url))
    res = run_daily(factory, args.as_of, settings=settings, force=args.force)
    print(json.dumps({"as_of": str(res.as_of), "status": res.status, "errors": res.errors}))


if __name__ == "__main__":
    main()
