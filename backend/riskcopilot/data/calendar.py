"""Calendar alignment: US, India and FX markets trade on different days."""

import pandas as pd


def master_calendar(raw: pd.DataFrame, anchor: str = "SPY") -> pd.DatetimeIndex:
    """Business days on which the anchor (NYSE-listed SPY) traded."""
    return pd.DatetimeIndex(raw[anchor].dropna().index).sort_values()


def align(raw: pd.DataFrame, calendar: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reindex to the master calendar and forward-fill gaps.

    Returns the aligned prices and a boolean mask of which cells were filled, so every fill
    is recorded rather than silently applied.
    """
    on_cal = raw.reindex(raw.index.union(calendar)).sort_index().ffill().reindex(calendar)
    observed = raw.reindex(calendar).notna()
    filled = on_cal.notna() & ~observed
    return on_cal, filled


def to_usd(prices: pd.DataFrame, inverse: set[str]) -> pd.DataFrame:
    """Express every instrument as USD per unit; e.g. INR=X (INR per USD) becomes 1/INR=X,
    so a long-INR position loses when INR=X rises."""
    out = prices.copy()
    for col in inverse & set(out.columns):
        out[col] = 1.0 / out[col]
    return out
