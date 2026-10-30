"""Turn raw quoted prices into clean USD prices, returns and a list of data issues."""

from dataclasses import dataclass

import pandas as pd

from riskcopilot.data import quality
from riskcopilot.data.calendar import align, master_calendar, to_usd
from riskcopilot.engine.returns import log_returns, simple_returns
from riskcopilot.reference import Instrument


@dataclass
class MarketData:
    prices_usd: pd.DataFrame
    filled: pd.DataFrame
    simple: pd.DataFrame
    log: pd.DataFrame
    issues: list[quality.Issue]

    @property
    def blocking(self) -> list[quality.Issue]:
        return [i for i in self.issues if i.severity == "critical"]


def build_market_data(
    raw: pd.DataFrame, instruments: list[Instrument], as_of: pd.Timestamp | None = None
) -> MarketData:
    tickers = [i.ticker for i in instruments]
    raw = raw.reindex(columns=tickers)
    cal = master_calendar(raw)
    if as_of is not None:
        cal = cal[cal <= as_of]
    as_of = cal[-1]
    aligned, filled = align(raw, cal)
    usd = to_usd(aligned, {i.ticker for i in instruments if i.inverse_quote})
    # Start where every instrument has a price, so returns have no gaps.
    first = usd.dropna().index[0]
    usd, filled = usd.loc[first:], filled.loc[first:]
    simple, logr = simple_returns(usd), log_returns(usd)

    issues = (
        quality.check_missing(usd, as_of)
        + quality.check_coverage(raw, as_of)
        + quality.check_stale(raw.reindex(cal), as_of)
        + quality.check_jumps(simple, as_of)
        + quality.fill_issues(filled, as_of)
    )
    return MarketData(usd, filled, simple, logr, issues)
