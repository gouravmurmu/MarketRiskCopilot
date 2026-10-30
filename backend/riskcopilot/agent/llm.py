"""Claude client, prompts and trace logging shared by the daily workflow and the chat."""

import hashlib
import time
import uuid
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from riskcopilot.config import Settings
from riskcopilot.db import models as m

# Server-side fallback: if the model declines a request, the API re-runs it on Anthropic's
# recommended fallback model inside the same call instead of returning a refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

RULES = """\
Rules:
- Use only numbers returned by tools. Never estimate, compute or round to a new figure; \
copy figures from the tool outputs (you may express USD in $k with one decimal and \
fractions as percentages with one decimal).
- If data is missing, stale or flagged, say so.
- No investment advice or trade recommendations. What-if analysis is hypothetical only.
- Limit status (ok, warning, breach) is decided by the rule engine; report it, never judge it.
- Only mention tickers that are in the portfolio.
- Style: concise, neutral risk-report tone. USD in $k with one decimal; percentages with one \
decimal; dates as YYYY-MM-DD."""

DAILY_SYSTEM = f"""\
You are a market risk analyst assistant for a single USD multi-asset portfolio (about $10M \
across equities, rates, credit, commodities and FX). You write the daily risk commentary \
from the tool outputs you are given.

{RULES}

The primary metric is the 1-day 99% historical-simulation VaR on a 500-day window (hs_500). \
Lead with it. In drivers, report the effects from get_var_attribution for hs_500 with their \
exact amounts. List every limit that is in warning or breach, plus the portfolio limit. \
Return JSON matching the schema."""

CHAT_SYSTEM = f"""\
You are a market risk analyst assistant for a single USD multi-asset portfolio (about $10M \
across equities, rates, credit, commodities and FX). Answer the analyst's questions using the \
tools; call them for every figure you mention. Default to the latest date unless the analyst \
names one.

{RULES}

Answer in a few short sentences or a small markdown table. Name the tools you relied on at \
the end in one line, like: Sources: get_risk_summary, get_limit_status."""


def make_client(settings: Settings) -> Any:
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3)


def request_kwargs(settings: Settings) -> dict[str, Any]:
    return {
        "model": settings.agent_model,
        "thinking": {"type": "adaptive"},
        "betas": [FALLBACK_BETA],
        "fallbacks": "default",
    }


def new_trace_id() -> str:
    return uuid.uuid4().hex


def output_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Tracer:
    """Writes one agent_traces row per tool call or model call."""

    def __init__(self, session: Session, mode: str, as_of: date | None) -> None:
        self.session, self.mode, self.as_of = session, mode, as_of
        self.trace_id = new_trace_id()
        self.step = 0

    def log(
        self,
        *,
        tool: str | None = None,
        args: dict[str, Any] | None = None,
        output: str | None = None,
        tokens: int | None = None,
        started: float | None = None,
        model: str | None = None,
    ) -> None:
        self.step += 1
        self.session.add(
            m.AgentTrace(
                trace_id=self.trace_id,
                as_of=self.as_of,
                mode=self.mode,
                step=self.step,
                tool_name=tool,
                args_json=args,
                output_hash=None if output is None else output_hash(output),
                tokens=tokens,
                latency_ms=None if started is None else int((time.perf_counter() - started) * 1e3),
                model=model,
            )
        )
        self.session.flush()


def usage_tokens(resp: Any) -> int | None:
    u = getattr(resp, "usage", None)
    if u is None:
        return None
    return int((getattr(u, "input_tokens", 0) or 0) + (getattr(u, "output_tokens", 0) or 0))


def text_of(resp: Any) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
