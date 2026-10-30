"""Read-only tools the copilot can call. Each one is a thin wrapper over the API route
functions or the stored engine outputs, so the agent sees exactly what the dashboard shows.

No tool writes to the database. `run_what_if` computes on a copy of the positions.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from riskcopilot import reference
from riskcopilot.api import schemas as s
from riskcopilot.api.deps import resolve_as_of
from riskcopilot.api.routes import controls, risk, whatif
from riskcopilot.config import get_settings
from riskcopilot.db import models as m
from riskcopilot.db import repo
from riskcopilot.engine.returns import next_day_pnl
from riskcopilot.engine.runner import MODEL_BY_KEY


class ToolError(Exception):
    """A tool could not answer; the message goes back to the model as an error result."""


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of: date | None = Field(None, description="Business date YYYY-MM-DD; latest if omitted")


class _ModelArgs(_Args):
    model: str = Field("hs_500", description="Model key, e.g. hs_500, pn_ewma, mc_ewma")
    confidence: float = Field(0.99, description="0.99 or 0.975")


class _ContribArgs(_ModelArgs):
    level: str = Field("position", pattern="^(position|asset_class)$")
    n: int = Field(5, ge=1, le=15)


class _MovesArgs(_Args):
    tickers: list[str] | None = Field(None, description="Portfolio tickers; all if omitted")


class _WhatIfArgs(_Args):
    change_exposure: dict[str, float] = Field(
        default_factory=dict, description="USD change per ticker, e.g. {'NVDA': -400000}"
    )
    set_exposure: dict[str, float] = Field(
        default_factory=dict, description="Target USD exposure per ticker, e.g. {'NVDA': 0}"
    )


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[_Args]
    fn: Callable[[Session, Any], Any]
    extra: dict[str, Any] = field(default_factory=dict)

    def schema(self, eager: bool = False) -> dict[str, Any]:
        js = self.args.model_json_schema()
        js.pop("title", None)
        for p in js.get("properties", {}).values():
            p.pop("title", None)
        out: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "input_schema": js,
        }
        if eager:
            out["eager_input_streaming"] = True
        return out

    def run(self, session: Session, raw: dict[str, Any]) -> Any:
        try:
            args = self.args.model_validate(raw)
        except ValidationError as e:
            raise ToolError(f"Invalid input: {e.errors(include_url=False)}") from e
        try:
            return compact(self.fn(session, args))
        except HTTPException as e:
            raise ToolError(str(e.detail)) from e


def compact(x: Any) -> Any:
    """JSON-safe copy with floats rounded: whole dollars for amounts, 4 dp for ratios."""
    if isinstance(x, BaseModel):
        return compact(x.model_dump(mode="json"))
    if isinstance(x, dict):
        return {str(k): compact(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [compact(v) for v in x]
    if isinstance(x, float | np.floating):
        v = float(x)
        if not np.isfinite(v):
            return None
        return round(v) if abs(v) >= 100 else round(v, 4)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, date):
        return x.isoformat()
    return x


def _as_of(session: Session, a: _Args) -> date:
    return resolve_as_of(session, a.as_of)


def _check_model(key: str) -> None:
    if key not in MODEL_BY_KEY:
        raise ToolError(f"Unknown model {key!r}; choose from {list(MODEL_BY_KEY)}")


def get_risk_summary(session: Session, a: _Args) -> Any:
    out = risk.summary(session, _as_of(session, a))
    return {
        "as_of": out.as_of,
        "previous_as_of": out.previous_as_of,
        "primary_model": get_settings().primary_model,
        "figures": [f.model_dump(exclude={"method", "es_10d_usd"}) for f in out.figures],
    }


def get_var_attribution(session: Session, a: _ModelArgs) -> Any:
    _check_model(a.model)
    out = risk.attribution(session, _as_of(session, a), a.model, a.confidence)
    body = out.model_dump()
    for e in body["effects"]:
        if e["effect"] == "window_roll":  # scenarios are the job of get_scenario_rolloff
            e["detail"] = {
                "dropped": len(e["detail"].get("dropped", [])),
                "added": len(e["detail"].get("added", [])),
            }
    return body


def get_top_contributors(session: Session, a: _ContribArgs) -> Any:
    _check_model(a.model)
    as_of = _as_of(session, a)
    today = risk.contributors(session, as_of, a.model, a.confidence, a.level)
    prev_date = risk.previous_date(session, as_of)
    prev: dict[str, float] = {}
    if prev_date:
        try:
            p = risk.contributors(session, prev_date, a.model, a.confidence, a.level)
            prev = {i.key: i.component_var for i in p.items}
        except HTTPException:
            pass
    return {
        "as_of": as_of,
        "model": a.model,
        "confidence": a.confidence,
        "level": a.level,
        "total_var_usd": today.total_var_usd,
        "items": [
            {
                **i.model_dump(),
                "prev_component_var": prev.get(i.key),
                "change_usd": None if i.key not in prev else i.component_var - prev[i.key],
            }
            for i in today.items[: a.n]
        ],
    }


def get_market_moves(session: Session, a: _MovesArgs) -> Any:
    as_of = _as_of(session, a)
    returns = repo.load_returns(session)
    if returns.empty:
        raise ToolError("No returns stored yet")
    hist = returns.loc[: str(as_of)]
    if hist.empty or hist.index[-1].date() != as_of:
        raise ToolError(f"No returns on {as_of}")
    tickers = a.tickers or list(hist.columns)
    unknown = sorted(set(tickers) - set(hist.columns))
    if unknown:
        raise ToolError(f"Not in the portfolio: {unknown}")
    vol_now = hist.iloc[-20:].std() * np.sqrt(252)
    vol_prev = hist.iloc[-21:-1].std() * np.sqrt(252)
    corr_now = hist.iloc[-60:].corr()["SPY"]
    corr_prev = hist.iloc[-61:-1].corr()["SPY"]
    acls = reference.asset_class_of()
    return {
        "as_of": as_of,
        "note": "return_1d is the simple daily return in USD terms; vols are annualised 20-day",
        "moves": [
            {
                "ticker": t,
                "asset_class": acls.get(t),
                "return_1d": hist[t].iloc[-1],
                "vol_20d": vol_now[t],
                "vol_20d_change": vol_now[t] - vol_prev[t],
                "corr_spy_60d": corr_now[t],
                "corr_spy_60d_change": corr_now[t] - corr_prev[t],
            }
            for t in tickers
        ],
    }


def get_macro_context(session: Session, a: _Args) -> Any:
    as_of = _as_of(session, a)
    out = []
    for sid, label in reference.FRED_SERIES.items():
        rows = session.execute(
            select(m.MacroSeries.date, m.MacroSeries.value)
            .where(m.MacroSeries.series_id == sid, m.MacroSeries.date <= as_of)
            .order_by(m.MacroSeries.date.desc())
            .limit(2)
        ).all()
        if not rows:
            continue
        (d, v), prev = rows[0], (rows[1] if len(rows) > 1 else None)
        out.append(
            {
                "series": sid,
                "label": label,
                "date": d,
                "value": v,
                "change": None if prev is None else v - prev[1],
                "stale_days": (as_of - d).days,
            }
        )
    if not out:
        raise ToolError("No macro series stored (FRED data unavailable)")
    return {"as_of": as_of, "units": "yields/spreads in %, VIX in points", "series": out}


def get_limit_status(session: Session, a: _Args) -> Any:
    out = controls.limits(session, _as_of(session, a))
    if not out.items:
        raise ToolError(f"No limit checks on {out.as_of}")
    return out


def get_backtest_status(session: Session, a: _Args) -> Any:
    as_of = _as_of(session, a)
    settings = get_settings()
    end = session.scalar(
        select(func.max(m.BacktestResultRow.window_end)).where(
            m.BacktestResultRow.window_end <= as_of
        )
    )
    rows = session.scalars(
        select(m.BacktestResultRow).where(
            m.BacktestResultRow.window_end == end, m.BacktestResultRow.scope == "rolling_250"
        )
    ).all()
    tests = [
        {
            k: getattr(r, k)
            for k in ("model", "confidence", "T", "exceptions", "expected", "p_pof", "p_cc", "zone")
        }
        for r in rows
    ]
    # Recent exceptions of the primary model: next-day loss larger than VaR.
    var = repo.var_history(session, settings.primary_model, settings.primary_confidence)
    returns = repo.load_returns(session)
    recent: list[dict[str, Any]] = []
    if not returns.empty and not var.empty:
        pnl = next_day_pnl(returns, repo.position_history(session))
        both = (
            pd.concat({"var": var, "pnl": pnl}, axis=1, sort=True)
            .dropna()
            .loc[: str(as_of)]
            .iloc[-250:]
        )
        hits = both[-both["pnl"] > both["var"]]
        recent = [
            {"var_date": d.date(), "var_usd": r["var"], "next_day_pnl_usd": r["pnl"]}
            for d, r in hits.iloc[-5:].iterrows()
        ]
    return {
        "as_of": as_of,
        "window_end": end,
        "scope": "rolling_250",
        "primary_model": settings.primary_model,
        "tests": tests,
        "recent_primary_exceptions": recent,
    }


def get_scenario_rolloff(session: Session, a: _ModelArgs) -> Any:
    if not a.model.startswith("hs"):
        raise ToolError("Scenario roll-off applies to historical simulation models (hs_*)")
    _check_model(a.model)
    out = risk.attribution(session, _as_of(session, a), a.model, a.confidence)
    roll = next((e for e in out.effects if e.effect == "window_roll"), None)
    if roll is None:
        raise ToolError(f"No window-roll attribution for {a.model} on {out.as_of}")
    return {
        "as_of": out.as_of,
        "model": a.model,
        "confidence": a.confidence,
        "window_roll_usd": roll.amount_usd,
        "note": "pnl is the scenario P&L on today's positions; in_tail = inside the VaR tail",
        **roll.detail,
    }


def get_data_quality_issues(session: Session, a: _Args) -> Any:
    out = controls.data_quality(session, _as_of(session, a))
    return {
        "as_of": out.as_of,
        "blocking": out.blocking,
        "issues": [i.model_dump(exclude={"id"}) for i in out.issues if not i.resolved],
    }


def run_what_if(session: Session, a: _WhatIfArgs) -> Any:
    if not a.change_exposure and not a.set_exposure:
        raise ToolError("Give change_exposure or set_exposure")
    req = s.WhatIfRequest(
        as_of=a.as_of, set_exposure=a.set_exposure, change_exposure=a.change_exposure
    )
    out = whatif.whatif(session, req)
    changed = set(a.set_exposure) | set(a.change_exposure)
    return {
        "as_of": out.as_of,
        "hypothetical": True,
        "exposures_changed": {
            t: {"before": out.exposures_before.get(t, 0.0), "after": out.exposures_after[t]}
            for t in sorted(changed)
        },
        "figures": out.figures,
        "limits_after": out.limits_after,
        "limits_before": out.limits_before,
    }


TOOLS: list[Tool] = [
    Tool(
        "get_risk_summary",
        "VaR and ES (1-day and 10-day, USD) for every model at 99% and 97.5%, with the "
        "day-over-day change. Start here.",
        _Args,
        get_risk_summary,
    ),
    Tool(
        "get_var_attribution",
        "Explains the day-over-day VaR change of one model as effects that sum exactly to the "
        "change: position, volatility and correlation (parametric), position and window_roll "
        "(historical), or position and market_data (others).",
        _ModelArgs,
        get_var_attribution,
    ),
    Tool(
        "get_top_contributors",
        "Largest Euler component VaRs by position or asset class, with their change since the "
        "previous day. Components sum to total VaR.",
        _ContribArgs,
        get_top_contributors,
    ),
    Tool(
        "get_market_moves",
        "Daily return, 20-day volatility and its change, and 60-day correlation to SPY and its "
        "change, per ticker.",
        _MovesArgs,
        get_market_moves,
    ),
    Tool(
        "get_macro_context",
        "Latest level and daily change of Treasury yields, the 2s10s curve, VIX, the high-yield "
        "spread, USD/INR and SOFR.",
        _Args,
        get_macro_context,
    ),
    Tool(
        "get_limit_status",
        "Standalone VaR limit utilisation and status (ok, warning at 80%, breach at 100%) for the "
        "portfolio and each asset class. Status is decided by the rule engine.",
        _Args,
        get_limit_status,
    ),
    Tool(
        "get_backtest_status",
        "Rolling 250-day backtest results per model (exceptions, Kupiec and Christoffersen "
        "p-values, Basel zone) and the latest exceptions of the primary model.",
        _Args,
        get_backtest_status,
    ),
    Tool(
        "get_scenario_rolloff",
        "Historical scenarios that entered and left a historical-simulation window today, with "
        "their P&L on today's positions and whether they sit in the VaR tail.",
        _ModelArgs,
        get_scenario_rolloff,
    ),
    Tool(
        "get_data_quality_issues",
        "Open data quality issues for the date (missing, stale, filled or jumping prices) and "
        "whether any of them blocks the run.",
        _Args,
        get_data_quality_issues,
    ),
    Tool(
        "run_what_if",
        "Hypothetical VaR, ES and limit use after exposure changes. Works on a copy and never "
        "changes real positions. Use for 'what if we cut X' questions only.",
        _WhatIfArgs,
        run_what_if,
    ),
]
TOOL_BY_NAME = {t.name: t for t in TOOLS}

# The daily workflow gathers these in a fixed order, so its input is identical every run.
DAILY_GATHER: list[tuple[str, dict[str, Any]]] = [
    ("get_risk_summary", {}),
    ("get_var_attribution", {"model": "hs_500"}),
    ("get_var_attribution", {"model": "pn_ewma"}),
    ("get_top_contributors", {"level": "asset_class", "n": 5}),
    ("get_top_contributors", {"level": "position", "n": 5}),
    ("get_market_moves", {}),
    ("get_macro_context", {}),
    ("get_limit_status", {}),
    ("get_backtest_status", {}),
    ("get_scenario_rolloff", {"model": "hs_500"}),
    ("get_data_quality_issues", {}),
]


def call_tool(session: Session, name: str, raw: dict[str, Any]) -> tuple[bool, Any]:
    """Run a tool. Returns (ok, output); on failure the output is the error message."""
    tool = TOOL_BY_NAME.get(name)
    if tool is None:
        return False, f"Unknown tool {name!r}"
    try:
        return True, tool.run(session, raw)
    except ToolError as e:
        return False, str(e)


def dumps(x: Any) -> str:
    return json.dumps(x, separators=(",", ":"), default=str)
