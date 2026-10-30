from datetime import date

import pytest
from sqlalchemy import func, select

from riskcopilot.config import Settings
from riskcopilot.db import models as m
from riskcopilot.db.session import make_engine, make_session_factory
from riskcopilot.jobs.eod import run_eod
from tests.conftest import FakePrices


@pytest.fixture
def db(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    m.Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_eod_end_to_end_and_idempotent(db, prices):
    settings = Settings(history_start="2018-01-01", mc_paths=2_000)
    as_of = date(2021, 3, 31)
    res = run_eod(db, FakePrices(prices), None, settings, as_of)
    assert res.status == "ok" and res.as_of == as_of
    n_dates = len(res.dates_run)
    assert n_dates > 50

    with db() as s:
        runs = s.scalar(select(func.count()).select_from(m.RiskRun))
        # Stressed VaR only starts once its window (to Jan 2021) is in history.
        svar = s.scalar(
            select(func.count()).select_from(m.RiskRun).where(m.RiskRun.model == "svar")
        )
        assert svar > 0
        assert runs == n_dates * 8 * 2 + svar
        checks = s.scalars(select(m.LimitCheckRow).where(m.LimitCheckRow.as_of == as_of)).all()
        assert len(checks) == 6
        attr = s.scalars(
            select(m.VarAttribution).where(m.VarAttribution.run_id == f"{as_of}:hs_500:0.99")
        ).all()
        assert {a.effect for a in attr} == {"position", "window_roll"}
        bt = s.scalars(select(m.BacktestResultRow)).all()
        assert {b.scope for b in bt} == {"rolling_250", "full"}
        prices_n = s.scalar(select(func.count()).select_from(m.Price))

    # Rerun the same day: only that day is recomputed and nothing duplicates.
    res2 = run_eod(db, FakePrices(prices), None, settings, as_of)
    assert res2.dates_run == [as_of]
    with db() as s:
        assert s.scalar(select(func.count()).select_from(m.RiskRun)) == runs
        assert s.scalar(select(func.count()).select_from(m.Price)) == prices_n


def test_eod_blocks_on_critical_issue(db, prices):
    bad = prices.copy()
    bad.loc[bad.index[-1], "NVDA"] = bad["NVDA"].iloc[-2] * 2
    settings = Settings(history_start="2018-01-01", mc_paths=2_000)
    res = run_eod(db, FakePrices(bad), None, settings, date(2021, 3, 31))
    assert res.status == "blocked"
    assert any("jump" in b for b in res.blocking)
    with db() as s:
        assert s.scalar(select(func.count()).select_from(m.RiskRun)) == 0
