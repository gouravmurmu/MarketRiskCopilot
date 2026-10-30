"""End-of-day batch: ingest -> data checks -> engine -> attribution -> limits -> backtests.

Every step is idempotent, so a rerun of a day replaces its results. The job stops before
the engine if a critical data issue on the as-of date is unresolved.

    python -m riskcopilot.jobs.eod                 # latest business day
    python -m riskcopilot.jobs.eod --as-of 2026-10-29
"""

import argparse
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sqlalchemy.orm import Session, sessionmaker

from riskcopilot import reference
from riskcopilot.config import Settings, get_settings
from riskcopilot.data.ingest import MarketData, build_market_data
from riskcopilot.data.sources import Fred, MacroSource, PriceSource, YahooWithStooqFallback
from riskcopilot.db import models as m
from riskcopilot.db import repo
from riskcopilot.db.session import make_engine, make_session_factory
from riskcopilot.engine.backtest import run_backtest
from riskcopilot.engine.limits import check_limit
from riskcopilot.engine.returns import next_day_pnl
from riskcopilot.engine.runner import (
    EVALUATORS,
    RunContext,
    attribute_change,
    run_models,
    standalone_by_asset_class,
)

log = logging.getLogger("riskcopilot.eod")

MIN_HISTORY = 500  # longest model window
ATTRIBUTION_DAYS = 60  # days of attribution history kept for the dashboard on a backfill
REDOWNLOAD_DAYS = 7  # re-pull the last few days in case of late corrections


@dataclass
class EodResult:
    as_of: date
    status: str  # ok | blocked
    dates_run: list[date] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)


def code_version() -> str:
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "dev"


def ingest(
    session: Session,
    prices: PriceSource,
    macro: MacroSource | None,
    settings: Settings,
    as_of: date | None,
) -> MarketData:
    cached = repo.load_raw_prices(session)
    if cached.empty:
        start = settings.history_start
    else:
        start = str((cached.index.max() - pd.Timedelta(days=REDOWNLOAD_DAYS)).date())
    end = str(pd.Timestamp(as_of) + pd.Timedelta(days=1))[:10] if as_of else None
    fresh = prices.prices(list(reference.INSTRUMENTS), start, end)
    raw = fresh.combine_first(cached) if not cached.empty else fresh
    md = build_market_data(raw, list(reference.INSTRUMENTS), pd.Timestamp(as_of) if as_of else None)

    since = None if cached.empty else pd.Timestamp(start)
    repo.write_market_data(
        session, raw, md.prices_usd, md.filled, md.simple, md.log, since, source="yfinance"
    )
    if macro is not None:
        repo.write_macro(session, macro.series(list(reference.FRED_SERIES), start))
    issue_dates = {i.date.date() for i in md.issues}
    issue_dates.add(md.prices_usd.index[-1].date())
    repo.replace_issues(session, issue_dates, md.issues)
    return md


def run_engine_for_date(
    session: Session,
    returns: pd.DataFrame,
    d: pd.Timestamp,
    prev: pd.Timestamp | None,
    ctx: RunContext,
    settings: Settings,
    version: str,
    with_attribution: bool,
) -> None:
    acls = reference.asset_class_of()
    hist = returns.loc[:d]
    exposures = repo.positions_on(session, d.date())
    repo.clear_runs(session, d.date())

    runs = run_models(hist, exposures, acls, ctx)
    for r in runs:
        rid = repo.run_id(d.date(), r.model, r.confidence)
        session.add(
            m.RiskRun(
                run_id=rid,
                as_of=d.date(),
                model=r.model,
                method=r.method,
                confidence=r.confidence,
                window=r.window,
                var_usd=r.var,
                es_usd=r.es,
                var_10d_usd=r.var_10d,
                es_10d_usd=r.es_10d,
                code_version=version,
                seed=settings.mc_seed if r.method == "monte_carlo" else None,
            )
        )
    # No ORM relationship links the tables, so flush the parent rows first: Postgres
    # checks the foreign key on every insert.
    session.flush()
    for r in runs:
        rid = repo.run_id(d.date(), r.model, r.confidence)
        session.add_all(
            m.RiskContribution(
                run_id=rid,
                level=level,
                key=c.key,
                exposure_usd=c.exposure,
                component_var=c.component_var,
                marginal_var=c.marginal_var,
            )
            for level, cs in (("position", r.positions), ("asset_class", r.asset_classes))
            for c in cs
        )
    session.flush()

    if with_attribution and prev is not None:
        hist_prev = returns.loc[:prev]
        exp_prev = repo.positions_on(session, prev.date())
        for r in runs:
            effects = attribute_change(
                r.model, hist_prev, hist, exp_prev, exposures, r.confidence, ctx
            )
            rid = repo.run_id(d.date(), r.model, r.confidence)
            session.add_all(
                m.VarAttribution(
                    run_id=rid, effect=e.effect, amount_usd=e.amount, detail_json=e.detail
                )
                for e in effects
            )

    # Limits are set on standalone 1-day VaR of the primary model.
    values = standalone_by_asset_class(
        settings.primary_model, hist, exposures, acls, settings.primary_confidence, ctx
    )
    lim_ids = repo.limit_ids(session)
    rows = []
    for scope, (limit_usd, warn_pct) in repo.limits_by_scope(session).items():
        if scope in values:
            c = check_limit(scope, values[scope], limit_usd, warn_pct)
            rows.append(
                {
                    "as_of": d.date(),
                    "limit_id": lim_ids[scope],
                    "value_usd": c.value,
                    "utilisation": c.utilisation,
                    "status": c.status,
                }
            )
    repo.upsert(session, m.LimitCheckRow, rows)


def run_backtests(session: Session, returns: pd.DataFrame, as_of: pd.Timestamp) -> None:
    """Compare VaR on day t with the hypothetical P&L on t+1 of day t's positions."""
    pnl = next_day_pnl(returns, repo.position_history(session))

    rows = []
    for model in EVALUATORS:
        for conf in (0.99, 0.975):
            var = repo.var_history(session, model, conf)
            both = pd.concat([var, pnl], axis=1, join="inner").dropna()
            both = both.loc[:as_of]
            if len(both) < 20:
                continue
            for scope, sample in (("rolling_250", both.iloc[-250:]), ("full", both)):
                b = run_backtest(sample.iloc[:, 0].to_numpy(), sample.iloc[:, 1].to_numpy(), conf)
                rows.append(
                    {
                        "model": model,
                        "confidence": conf,
                        "window_end": as_of.date(),
                        "scope": scope,
                        **b.__dict__,
                    }
                )
    repo.upsert(session, m.BacktestResultRow, rows)


def run_eod(
    session_factory: sessionmaker[Session],
    prices: PriceSource,
    macro: MacroSource | None = None,
    settings: Settings | None = None,
    as_of: date | None = None,
) -> EodResult:
    settings = settings or get_settings()
    version = code_version()
    timings: dict[str, float] = {}
    t0 = time.perf_counter()

    with session_factory.begin() as session:
        repo.seed_reference(session)
        md = ingest(session, prices, macro, settings, as_of)
    run_date = md.prices_usd.index[-1]
    timings["ingest"] = time.perf_counter() - t0

    with session_factory() as session:
        blocking = repo.unresolved_critical(session, run_date.date())
    if blocking:
        msgs = [f"{b.check}: {b.detail} (instrument {b.instrument_id})" for b in blocking]
        log.error("blocked by %d critical data issue(s): %s", len(msgs), msgs)
        return EodResult(run_date.date(), "blocked", blocking=msgs, timings=timings)

    returns = md.simple
    ctx = RunContext(
        settings.mc_paths, settings.mc_seed, settings.stress_start, settings.stress_end
    )
    with session_factory() as session:
        done = repo.existing_run_dates(session)
    eligible = returns.index[MIN_HISTORY - 1 :]
    todo = [d for d in eligible if d.date() not in done or d == run_date]
    attribution_from = eligible[-ATTRIBUTION_DAYS:][0] if len(eligible) else run_date

    t1 = time.perf_counter()
    for n, d in enumerate(todo):
        pos = eligible.get_loc(d)
        prev = eligible[pos - 1] if pos > 0 else None
        with session_factory.begin() as session:
            run_engine_for_date(
                session, returns, d, prev, ctx, settings, version, d >= attribution_from
            )
        if n % 100 == 0:
            log.info("engine %s (%d/%d)", d.date(), n + 1, len(todo))
    timings["engine"] = time.perf_counter() - t1

    t2 = time.perf_counter()
    with session_factory.begin() as session:
        run_backtests(session, returns, run_date)
    timings["backtest"] = time.perf_counter() - t2

    log.info("done %s: %d date(s), timings %s", run_date.date(), len(todo), timings)
    return EodResult(run_date.date(), "ok", [d.date() for d in todo], timings=timings)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    args = parser.parse_args()
    settings = get_settings()
    engine = make_engine(settings.database_url)
    result = run_eod(
        make_session_factory(engine),
        YahooWithStooqFallback(),
        Fred(settings.fred_api_key),
        settings,
        args.as_of,
    )
    if result.status != "ok":
        raise SystemExit(f"EOD blocked on {result.as_of}: {result.blocking}")


if __name__ == "__main__":
    main()
