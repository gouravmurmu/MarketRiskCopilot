import numpy as np
import pandas as pd

from riskcopilot.data import quality
from riskcopilot.data.calendar import align, to_usd
from riskcopilot.data.ingest import build_market_data
from riskcopilot.reference import INSTRUMENTS


def test_stale_price_detected(prices):
    raw = prices.copy()
    as_of = raw.index[-1]
    raw.loc[raw.index[-4:], "GLD"] = raw["GLD"].iloc[-5]
    issues = quality.check_stale(raw, as_of)
    assert [(i.ticker, i.check) for i in issues] == [("GLD", "stale")]


def test_gap_is_filled_and_recorded(prices):
    raw = prices.copy()
    raw.loc[raw.index[-1], "INDA"] = np.nan
    aligned, filled = align(raw, raw.index)
    assert filled.loc[raw.index[-1], "INDA"]
    assert aligned.loc[raw.index[-1], "INDA"] == raw["INDA"].dropna().iloc[-1]


def test_jump_on_as_of_is_critical(prices):
    raw = prices.copy()
    raw.loc[raw.index[-1], "SPY"] = raw["SPY"].iloc[-2] * 1.4
    md = build_market_data(raw, list(INSTRUMENTS))
    assert any(i.ticker == "SPY" and i.check == "jump" for i in md.blocking)


def test_coverage_flags_dead_feed(prices):
    raw = prices.copy()
    raw.loc[raw.index[-10:], "HYG"] = np.nan
    md = build_market_data(raw, list(INSTRUMENTS))
    assert any(i.ticker == "HYG" and i.check == "coverage" for i in md.blocking)


def test_clean_data_has_no_blocking_issues(prices):
    assert build_market_data(prices, list(INSTRUMENTS)).blocking == []


def test_inverse_fx_quote():
    df = pd.DataFrame({"INR=X": [80.0, 88.0]})
    usd = to_usd(df, {"INR=X"})
    # INR weakens 10% vs USD -> long INR loses ~9.1%
    assert usd["INR=X"].pct_change().iloc[-1] == np.float64(80 / 88 - 1)
