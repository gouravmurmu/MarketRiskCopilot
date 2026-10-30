"""Returns and portfolio P&L."""

import numpy as np
import pandas as pd


def simple_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change(fill_method=None).iloc[1:]


def log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return np.log(prices).diff().iloc[1:]


def exposure_vector(exposures: dict[str, float], columns: pd.Index) -> np.ndarray:
    """USD exposures aligned to the return columns (0 for instruments not held)."""
    return np.array([exposures.get(c, 0.0) for c in columns], dtype=float)


def portfolio_pnl(returns: pd.DataFrame, exposures: dict[str, float]) -> pd.Series:
    """Linear P&L: dP_t = w . r_t"""
    w = exposure_vector(exposures, returns.columns)
    return pd.Series(returns.to_numpy() @ w, index=returns.index, name="pnl")
