"""Data checks that run before any risk calculation.

A critical issue on the as-of date blocks the risk run until an analyst resolves it.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

STALE_DAYS = 3
JUMP_SIGMAS = 6.0
MAX_LAG_DAYS = 3


@dataclass(frozen=True)
class Issue:
    date: pd.Timestamp
    ticker: str | None
    check: str  # missing | stale | jump | coverage | fill
    severity: str  # info | warning | critical
    detail: str


def check_missing(prices: pd.DataFrame, as_of: pd.Timestamp) -> list[Issue]:
    if as_of not in prices.index:
        return [Issue(as_of, None, "missing", "critical", "no prices on the as-of date")]
    row = prices.loc[as_of]
    return [
        Issue(as_of, str(t), "missing", "critical", "no price on the as-of date")
        for t in row.index[row.isna()]
    ]


def check_stale(raw: pd.DataFrame, as_of: pd.Timestamp, days: int = STALE_DAYS) -> list[Issue]:
    """Observed price unchanged for `days` or more consecutive observations up to as_of."""
    issues = []
    for t in raw.columns:
        s = raw[t].loc[:as_of].dropna()
        if len(s) <= days:
            continue
        tail = s.iloc[-(days + 1) :]
        if np.allclose(tail.to_numpy(), tail.iloc[-1]):
            issues.append(
                Issue(as_of, str(t), "stale", "warning", f"price unchanged for {days}+ days")
            )
    return issues


def check_jumps(
    returns: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    sigmas: float = JUMP_SIGMAS,
    lookback: int = 250,
) -> list[Issue]:
    """Returns beyond `sigmas` x trailing std (excluding the day itself).

    On the as-of date a jump is critical and held for review; in history it is logged as info.
    """
    std = returns.rolling(lookback, min_periods=60).std().shift(1)
    z = returns / std
    issues = []
    hits = z.abs() > sigmas
    for d, t in zip(*np.nonzero(hits.to_numpy()), strict=True):
        date = returns.index[d]
        ticker = str(returns.columns[t])
        sev = "critical" if as_of is not None and date == as_of else "info"
        r, zz = returns.iat[d, t], z.iat[d, t]
        issues.append(Issue(date, ticker, "jump", sev, f"return {r:+.2%} is {zz:+.1f} sigma"))
    return issues


def check_coverage(
    raw: pd.DataFrame, as_of: pd.Timestamp, max_lag: int = MAX_LAG_DAYS
) -> list[Issue]:
    """Latest observed price per instrument must be within `max_lag` business days."""
    issues = []
    for t in raw.columns:
        last = raw[t].loc[:as_of].last_valid_index()
        if last is None:
            issues.append(Issue(as_of, str(t), "coverage", "critical", "no history"))
            continue
        lag = len(pd.bdate_range(last, as_of)) - 1
        if lag > max_lag:
            issues.append(
                Issue(
                    as_of,
                    str(t),
                    "coverage",
                    "critical",
                    f"last price {last.date()}, {lag} bdays old",
                )
            )
    return issues


def fill_issues(filled: pd.DataFrame, as_of: pd.Timestamp) -> list[Issue]:
    if as_of not in filled.index:
        return []
    row = filled.loc[as_of]
    return [
        Issue(as_of, str(t), "fill", "info", "forward-filled (market holiday or missing print)")
        for t in row.index[row.to_numpy(dtype=bool)]
    ]
