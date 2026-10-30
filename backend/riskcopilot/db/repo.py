"""Database reads and idempotent writes used by the daily job."""

from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import Table, delete, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from riskcopilot import reference
from riskcopilot.db import models as m

CHUNK = 1000


def upsert(session: Session, model: type[m.Base], rows: Sequence[dict[str, Any]]) -> None:
    """INSERT ... ON CONFLICT (primary key) DO UPDATE, on Postgres or SQLite."""
    if not rows:
        return
    table: Table = model.__table__  # type: ignore[assignment]
    pk = [c.name for c in table.primary_key.columns]
    dialect = session.get_bind().dialect.name
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
    for i in range(0, len(rows), CHUNK):
        stmt = insert(table).values(list(rows[i : i + CHUNK]))
        update_cols = {c.name: stmt.excluded[c.name] for c in table.columns if c.name not in pk}
        stmt = stmt.on_conflict_do_update(index_elements=pk, set_=update_cols)
        session.execute(stmt)


def seed_reference(session: Session) -> None:
    """Instruments, positions (base book + simulated trades) and limits. Safe to rerun."""
    upsert(
        session,
        m.InstrumentRow,
        [
            {
                "id": n + 1,
                "ticker": i.ticker,
                "name": i.name,
                "asset_class": i.asset_class,
                "currency": i.currency,
            }
            for n, i in enumerate(reference.INSTRUMENTS)
        ],
    )
    ids = instrument_ids(session)
    rows = [
        {
            "portfolio_id": 1,
            "as_of": reference.BASE_POSITIONS_AS_OF,
            "instrument_id": ids[t],
            "quantity": None,
            "notional_usd": v,
        }
        for t, v in reference.BASE_POSITIONS.items()
    ]
    for d, _, _ in reference.SIMULATED_TRADES:
        book = reference.positions_on(d)
        rows += [
            {
                "portfolio_id": 1,
                "as_of": d,
                "instrument_id": ids[tk],
                "quantity": None,
                "notional_usd": book[tk],
            }
            for tk in book
        ]
    upsert(session, m.Position, rows)
    if session.scalar(select(m.Limit.id).limit(1)) is None:
        session.add_all(
            m.Limit(
                scope=s,
                limit_usd=v,
                warn_pct=reference.WARN_PCT,
                active_from=reference.BASE_POSITIONS_AS_OF,
            )
            for s, v in reference.LIMITS.items()
        )
    session.flush()


def instrument_ids(session: Session) -> dict[str, int]:
    return {r.ticker: r.id for r in session.scalars(select(m.InstrumentRow))}


def positions_on(session: Session, as_of: date) -> dict[str, float]:
    """Exposures from the latest position set on or before as_of."""
    latest = session.scalar(
        select(m.Position.as_of).where(m.Position.as_of <= as_of).order_by(m.Position.as_of.desc())
    )
    if latest is None:
        return {}
    q = (
        select(m.InstrumentRow.ticker, m.Position.notional_usd)
        .join(m.InstrumentRow, m.InstrumentRow.id == m.Position.instrument_id)
        .where(m.Position.as_of == latest)
    )
    return {t: float(v) for t, v in session.execute(q)}


def position_history(session: Session) -> dict[date, dict[str, float]]:
    """All position sets keyed by their as_of date."""
    q = select(m.Position.as_of, m.InstrumentRow.ticker, m.Position.notional_usd).join(
        m.InstrumentRow, m.InstrumentRow.id == m.Position.instrument_id
    )
    out: dict[date, dict[str, float]] = {}
    for d, t, v in session.execute(q):
        out.setdefault(d, {})[t] = float(v)
    return dict(sorted(out.items()))


def load_raw_prices(session: Session) -> pd.DataFrame:
    """Observed (unfilled) quoted closes cached from earlier runs."""
    q = (
        select(m.InstrumentRow.ticker, m.Price.date, m.Price.close)
        .join(m.InstrumentRow, m.InstrumentRow.id == m.Price.instrument_id)
        .where(m.Price.is_filled.is_(False))
    )
    df = pd.DataFrame(session.execute(q).all(), columns=["ticker", "date", "close"])
    if df.empty:
        return pd.DataFrame()
    wide = df.pivot(index="date", columns="ticker", values="close")
    wide.index = pd.DatetimeIndex(wide.index)
    return wide.sort_index()


def write_market_data(
    session: Session,
    raw: pd.DataFrame,
    prices_usd: pd.DataFrame,
    filled: pd.DataFrame,
    simple: pd.DataFrame,
    logr: pd.DataFrame,
    since: pd.Timestamp | None,
    source: str,
) -> None:
    ids = instrument_ids(session)
    p = prices_usd if since is None else prices_usd.loc[since:]
    price_rows, ret_rows = [], []
    for d, row in p.iterrows():
        for t, v in row.items():
            if pd.isna(v):
                continue
            is_filled = bool(filled.at[d, t])
            close = None if is_filled else raw.at[d, t] if d in raw.index else None
            price_rows.append(
                {
                    "instrument_id": ids[str(t)],
                    "date": d.date(),
                    "close": _f(close),
                    "adj_close": float(v),
                    "source": "ffill" if is_filled else source,
                    "is_filled": is_filled,
                }
            )
    r = simple if since is None else simple.loc[since:]
    for d, row in r.iterrows():
        for t, v in row.items():
            if pd.isna(v):
                continue
            ret_rows.append(
                {
                    "instrument_id": ids[str(t)],
                    "date": d.date(),
                    "simple_ret": float(v),
                    "log_ret": float(logr.at[d, t]),
                }
            )
    upsert(session, m.Price, price_rows)
    upsert(session, m.Return, ret_rows)


def _f(x: Any) -> float | None:
    return None if x is None or pd.isna(x) else float(x)


def write_macro(session: Session, macro: pd.DataFrame) -> None:
    rows = [
        {"series_id": str(sid), "date": d.date(), "value": float(v)}
        for sid in macro.columns
        for d, v in macro[sid].dropna().items()
    ]
    upsert(session, m.MacroSeries, rows)


def replace_issues(session: Session, dates: Iterable[date], issues: list[Any]) -> None:
    """Rewrite the unresolved issues for the given dates (resolved ones are kept)."""
    ids = instrument_ids(session)
    session.execute(
        delete(m.DataQualityIssue).where(
            m.DataQualityIssue.date.in_(list(dates)), m.DataQualityIssue.resolved.is_(False)
        )
    )
    resolved = {
        (r.date, r.instrument_id, r.check)
        for r in session.scalars(select(m.DataQualityIssue).where(m.DataQualityIssue.resolved))
    }
    for i in issues:
        key = (i.date.date(), ids.get(i.ticker) if i.ticker else None, i.check)
        if key in resolved:
            continue
        session.add(
            m.DataQualityIssue(
                date=key[0],
                instrument_id=key[1],
                check=i.check,
                severity=i.severity,
                detail=i.detail,
            )
        )
    session.flush()


def unresolved_critical(session: Session, as_of: date) -> list[m.DataQualityIssue]:
    return list(
        session.scalars(
            select(m.DataQualityIssue).where(
                m.DataQualityIssue.date == as_of,
                m.DataQualityIssue.severity == "critical",
                m.DataQualityIssue.resolved.is_(False),
            )
        )
    )


def run_id(as_of: date, model: str, confidence: float) -> str:
    return f"{as_of.isoformat()}:{model}:{confidence:g}"


def existing_run_dates(session: Session) -> set[date]:
    return set(session.scalars(select(m.RiskRun.as_of).distinct()))


def clear_runs(session: Session, as_of: date) -> None:
    ids = list(session.scalars(select(m.RiskRun.run_id).where(m.RiskRun.as_of == as_of)))
    if not ids:
        return
    session.execute(delete(m.RiskContribution).where(m.RiskContribution.run_id.in_(ids)))
    session.execute(delete(m.VarAttribution).where(m.VarAttribution.run_id.in_(ids)))
    session.execute(delete(m.RiskRun).where(m.RiskRun.run_id.in_(ids)))


def var_history(session: Session, model: str, confidence: float) -> pd.Series:
    q = select(m.RiskRun.as_of, m.RiskRun.var_usd).where(
        m.RiskRun.model == model, m.RiskRun.confidence == confidence
    )
    rows = session.execute(q).all()
    s = pd.Series({pd.Timestamp(d): v for d, v in rows}, dtype=float)
    return s.sort_index()


def limit_ids(session: Session) -> dict[str, int]:
    return {r.scope: r.id for r in session.scalars(select(m.Limit))}


def limits_by_scope(session: Session) -> dict[str, tuple[float, float]]:
    return {r.scope: (r.limit_usd, r.warn_pct) for r in session.scalars(select(m.Limit))}
