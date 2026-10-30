"""Controls: portfolio, limits, backtests and data quality."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from riskcopilot import reference
from riskcopilot.api import schemas as s
from riskcopilot.api.deps import AsOfDep, SessionDep
from riskcopilot.config import get_settings
from riskcopilot.db import models as m
from riskcopilot.db import repo

router = APIRouter(tags=["controls"])


@router.get("/portfolio", response_model=s.Portfolio)
def portfolio(session: SessionDep, as_of: AsOfDep) -> s.Portfolio:
    books = repo.position_history(session)
    effective = max((d for d in books if d <= as_of), default=None)
    exposures = books.get(effective, {}) if effective else {}
    by_ticker = {i.ticker: i for i in reference.INSTRUMENTS}
    positions = [
        s.PositionOut(
            ticker=t, name=by_ticker[t].name, asset_class=by_ticker[t].asset_class, notional_usd=v
        )
        for t, v in exposures.items()
        if t in by_ticker
    ]
    order = {i.ticker: n for n, i in enumerate(reference.INSTRUMENTS)}
    positions.sort(key=lambda p: order[p.ticker])
    return s.Portfolio(
        as_of=as_of,
        positions_as_of=effective,
        total_usd=sum(exposures.values()),
        positions=positions,
    )


@router.get("/limits", response_model=s.Limits)
def limits(session: SessionDep, as_of: AsOfDep) -> s.Limits:
    q = (
        select(m.LimitCheckRow, m.Limit)
        .join(m.Limit, m.Limit.id == m.LimitCheckRow.limit_id)
        .where(m.LimitCheckRow.as_of == as_of)
    )
    items = [
        s.LimitOut(
            scope=lim.scope,
            limit_usd=lim.limit_usd,
            value_usd=c.value_usd,
            utilisation=c.utilisation,
            status=c.status,
            warn_pct=lim.warn_pct,
        )
        for c, lim in session.execute(q).all()
    ]
    order = list(reference.LIMITS)
    items.sort(key=lambda i: order.index(i.scope) if i.scope in order else 99)
    return s.Limits(as_of=as_of, model=get_settings().primary_model, items=items)


@router.get("/backtest", response_model=list[s.BacktestRow])
def backtest(
    session: SessionDep,
    model: Annotated[str | None, Query()] = None,
    confidence: Annotated[float | None, Query()] = None,
    scope: Annotated[str | None, Query(pattern="^(rolling_250|full)$")] = None,
) -> list[s.BacktestRow]:
    latest = session.scalar(select(func.max(m.BacktestResultRow.window_end)))
    q = select(m.BacktestResultRow).where(m.BacktestResultRow.window_end == latest)
    if model:
        q = q.where(m.BacktestResultRow.model == model)
    if confidence:
        q = q.where(m.BacktestResultRow.confidence == confidence)
    if scope:
        q = q.where(m.BacktestResultRow.scope == scope)
    return [s.BacktestRow.model_validate(r, from_attributes=True) for r in session.scalars(q).all()]


@router.get("/data-quality", response_model=s.DataQuality)
def data_quality(session: SessionDep, as_of: AsOfDep) -> s.DataQuality:
    tickers = {v: k for k, v in repo.instrument_ids(session).items()}
    rows = session.scalars(
        select(m.DataQualityIssue)
        .where(m.DataQualityIssue.date == as_of)
        .order_by(m.DataQualityIssue.severity, m.DataQualityIssue.id)
    ).all()
    issues = [
        s.IssueOut(
            id=r.id,
            date=r.date,
            ticker=tickers.get(r.instrument_id) if r.instrument_id else None,
            check=r.check,
            severity=r.severity,
            detail=r.detail,
            resolved=r.resolved,
        )
        for r in rows
    ]
    latest = session.execute(
        select(m.InstrumentRow.ticker, func.max(m.Price.date))
        .join(m.Price, m.Price.instrument_id == m.InstrumentRow.id)
        .where(m.Price.is_filled.is_(False))
        .group_by(m.InstrumentRow.ticker)
    ).all()
    return s.DataQuality(
        as_of=as_of,
        blocking=any(i.severity == "critical" and not i.resolved for i in issues),
        issues=issues,
        latest_price_dates={t: d for t, d in latest},
    )
