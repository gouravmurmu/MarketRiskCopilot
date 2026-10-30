"""Risk numbers: summary, history, contributors, attribution."""

from datetime import date
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from riskcopilot.api import schemas as s
from riskcopilot.api.deps import AsOfDep, SessionDep
from riskcopilot.config import get_settings
from riskcopilot.db import models as m
from riskcopilot.db import repo
from riskcopilot.engine.returns import next_day_pnl
from riskcopilot.engine.runner import MODEL_BY_KEY, MODELS

router = APIRouter(prefix="/risk", tags=["risk"])

ModelQ = Annotated[str | None, Query(description="Model key, e.g. hs_500")]
ConfQ = Annotated[float | None, Query(ge=0.9, le=0.999)]


def _model(model: str | None) -> str:
    key = model or get_settings().primary_model
    if key not in MODEL_BY_KEY:
        raise HTTPException(422, f"Unknown model {key!r}; choose from {list(MODEL_BY_KEY)}")
    return key


def _conf(conf: float | None) -> float:
    return conf if conf is not None else get_settings().primary_confidence


def previous_date(session: SessionDep, as_of: date) -> date | None:
    return session.scalar(select(func.max(m.RiskRun.as_of)).where(m.RiskRun.as_of < as_of))


@router.get("/summary", response_model=s.RiskSummary)
def summary(session: SessionDep, as_of: AsOfDep) -> s.RiskSummary:
    runs = session.scalars(select(m.RiskRun).where(m.RiskRun.as_of == as_of)).all()
    if not runs:
        raise HTTPException(404, f"No risk runs on {as_of}")
    prev = previous_date(session, as_of)
    prev_var = {}
    if prev:
        prev_var = {
            (r.model, r.confidence): r.var_usd
            for r in session.scalars(select(m.RiskRun).where(m.RiskRun.as_of == prev))
        }
    order = {spec.key: i for i, spec in enumerate(MODELS)}
    figures = []
    for r in sorted(runs, key=lambda r: (order.get(r.model, 99), -r.confidence)):
        pv = prev_var.get((r.model, r.confidence))
        figures.append(
            s.RiskFigure(
                model=r.model,
                method=r.method,
                label=MODEL_BY_KEY[r.model].label if r.model in MODEL_BY_KEY else r.model,
                confidence=r.confidence,
                var_usd=r.var_usd,
                es_usd=r.es_usd,
                var_10d_usd=r.var_10d_usd,
                es_10d_usd=r.es_10d_usd,
                prev_var_usd=pv,
                change_usd=None if pv is None else r.var_usd - pv,
                change_pct=None if not pv else r.var_usd / pv - 1,
            )
        )
    return s.RiskSummary(
        as_of=as_of, previous_as_of=prev, code_version=runs[0].code_version, figures=figures
    )


@router.get("/history", response_model=s.RiskHistory)
def history(
    session: SessionDep,
    model: ModelQ = None,
    confidence: ConfQ = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> s.RiskHistory:
    key, conf = _model(model), _conf(confidence)
    q = select(m.RiskRun.as_of, m.RiskRun.var_usd, m.RiskRun.es_usd).where(
        m.RiskRun.model == key, m.RiskRun.confidence == conf
    )
    if start:
        q = q.where(m.RiskRun.as_of >= start)
    if end:
        q = q.where(m.RiskRun.as_of <= end)
    rows = session.execute(q.order_by(m.RiskRun.as_of)).all()
    returns = repo.load_returns(session)
    pnl = next_day_pnl(returns, repo.position_history(session)) if not returns.empty else None
    points = []
    for d, var, es in rows:
        p = None if pnl is None else pnl.get(pd.Timestamp(d))
        p = None if p is None or pd.isna(p) else float(p)
        points.append(
            s.HistoryPoint(
                date=d,
                var_usd=var,
                es_usd=es,
                pnl_usd=p,
                exception=None if p is None else -p > var,
            )
        )
    return s.RiskHistory(model=key, confidence=conf, points=points)


@router.get("/contributors", response_model=s.Contributors)
def contributors(
    session: SessionDep,
    as_of: AsOfDep,
    model: ModelQ = None,
    confidence: ConfQ = None,
    level: Annotated[str, Query(pattern="^(position|asset_class)$")] = "position",
) -> s.Contributors:
    key, conf = _model(model), _conf(confidence)
    rid = repo.run_id(as_of, key, conf)
    run = session.get(m.RiskRun, rid)
    if run is None:
        raise HTTPException(404, f"No run {rid}")
    rows = session.scalars(
        select(m.RiskContribution).where(
            m.RiskContribution.run_id == rid, m.RiskContribution.level == level
        )
    ).all()
    items = sorted(
        (
            s.ContributionOut(
                key=r.key,
                exposure_usd=r.exposure_usd,
                component_var=r.component_var,
                marginal_var=r.marginal_var,
                share=r.component_var / run.var_usd if run.var_usd else 0.0,
            )
            for r in rows
        ),
        key=lambda c: -c.component_var,
    )
    return s.Contributors(
        as_of=as_of,
        model=key,
        confidence=conf,
        level=level,
        total_var_usd=run.var_usd,
        items=items,
    )


@router.get("/attribution", response_model=s.Attribution)
def attribution(
    session: SessionDep, as_of: AsOfDep, model: ModelQ = None, confidence: ConfQ = None
) -> s.Attribution:
    key, conf = _model(model), _conf(confidence)
    rid = repo.run_id(as_of, key, conf)
    run = session.get(m.RiskRun, rid)
    if run is None:
        raise HTTPException(404, f"No run {rid}")
    effects = session.scalars(select(m.VarAttribution).where(m.VarAttribution.run_id == rid)).all()
    prev = previous_date(session, as_of)
    prev_run = session.get(m.RiskRun, repo.run_id(prev, key, conf)) if prev else None
    order = ["position", "volatility", "correlation", "window_roll", "market_data"]
    return s.Attribution(
        as_of=as_of,
        model=key,
        confidence=conf,
        previous_var_usd=prev_run.var_usd if prev_run else None,
        var_usd=run.var_usd,
        effects=[
            s.EffectOut(effect=e.effect, amount_usd=e.amount_usd, detail=e.detail_json or {})
            for e in sorted(
                effects, key=lambda e: order.index(e.effect) if e.effect in order else 99
            )
        ],
    )
