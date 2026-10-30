"""Golden-date evaluation of the daily commentary. Calls the Claude API, so it costs money.

    python -m riskcopilot.agent.eval [--dates 2020-03-16,2024-08-05] [--out eval.md]

For each date it drafts the commentary (without storing it) and scores:
  valid         the numeric validator passed (within the retry budget)
  first_try     it passed on the first attempt
  direction     the headline says VaR rose/fell in line with the sign of the change
  limits        every warning or breach is in the draft
  top_driver    the largest attribution effect is among the drafted drivers
"""

import argparse
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from riskcopilot.agent import llm
from riskcopilot.agent.daily import draft_commentary
from riskcopilot.agent.draft import Draft
from riskcopilot.config import get_settings
from riskcopilot.db import models as m
from riskcopilot.db.session import make_engine, make_session_factory

GOLDEN = Path(__file__).with_name("golden_dates.json")
UP = re.compile(r"\b(rose|rises|increased|up|higher|climbed|jumped)\b", re.I)
DOWN = re.compile(r"\b(fell|falls|decreased|down|lower|declined|dropped|eased)\b", re.I)


def score(draft: Draft | None, outputs: dict[str, Any], attempts: int, ok: bool) -> dict[str, Any]:
    out: dict[str, Any] = {"valid": ok, "first_try": ok and attempts == 1, "attempts": attempts}
    if draft is None:
        return out | {"direction": False, "limits": False, "top_driver": False}
    summary = outputs.get("get_risk_summary") or {}
    hs = next(
        (
            f
            for f in summary.get("figures", [])
            if f["model"] == "hs_500" and f["confidence"] == 0.99
        ),
        None,
    )
    change = (hs or {}).get("change_usd") or 0.0
    up, down = bool(UP.search(draft.headline)), bool(DOWN.search(draft.headline))
    out["direction"] = (
        (change > 0 and up and not down) or (change < 0 and down and not up) or (change == 0)
    )
    limits = (outputs.get("get_limit_status") or {}).get("items", [])
    flagged = {x["scope"].lower() for x in limits if x["status"] != "ok"}
    out["limits"] = flagged <= {x.scope.lower() for x in draft.limits}
    attr: Any = next((v for k, v in outputs.items() if k.startswith("get_var_attribution")), {})
    effects = attr.get("effects", []) if isinstance(attr, dict) else []
    top = max(effects, key=lambda e: abs(e["amount_usd"]), default=None)
    out["top_driver"] = top is None or top["effect"] in {d.driver for d in draft.drivers}
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dates", default=None, help="Comma-separated dates; golden set if omitted"
    )
    parser.add_argument("--out", default="eval.md")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set")
    golden = json.loads(GOLDEN.read_text())
    dates = (
        [date.fromisoformat(d) for d in args.dates.split(",")]
        if args.dates
        else [date.fromisoformat(g["as_of"]) for g in golden]
    )
    factory = make_session_factory(make_engine(settings.database_url))
    client = llm.make_client(settings)
    rows = []
    for d in dates:
        with factory() as session:
            if session.query(m.RiskRun).filter_by(as_of=d).first() is None:
                logging.warning("no risk run on %s, skipped", d)
                continue
            tracer = llm.Tracer(session, "eval", d)
            draft, res, outputs = draft_commentary(session, d, client, settings, tracer)
            session.commit()
        rows.append({"as_of": str(d), **score(draft, outputs, res.attempts, res.status == "draft")})
        logging.info("%s: %s", d, rows[-1])
    keys = ["valid", "first_try", "direction", "limits", "top_driver"]
    lines = [
        f"# Commentary eval ({settings.agent_model}, effort {settings.agent_effort})",
        "",
        "| Date | " + " | ".join(keys) + " | Attempts |",
        "|---|" + "---|" * (len(keys) + 1),
    ]
    for r in rows:
        marks = " | ".join("yes" if r[k] else "**no**" for k in keys)
        lines.append(f"| {r['as_of']} | {marks} | {r['attempts']} |")
    if rows:
        rates = " | ".join(f"{sum(r[k] for r in rows) / len(rows):.0%}" for k in keys)
        lines.append(f"| **Pass rate** | {rates} | |")
    Path(args.out).write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
