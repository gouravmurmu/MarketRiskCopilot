"""Deterministic attribution of the day-over-day VaR change.

The effects always sum exactly to VaR(today) - VaR(yesterday), so the dashboard waterfall
and the agent's explanation reconcile to the reported numbers.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from riskcopilot.engine.covariance import corr_to_cov, cov_to_corr
from riskcopilot.engine.historical import historical_var_es
from riskcopilot.engine.parametric import normal_var_es


@dataclass(frozen=True)
class Effect:
    effect: str  # position | volatility | correlation | window_roll | market_data
    amount: float
    detail: dict[str, Any] = field(default_factory=dict)


def _position_detail(keys: list[str], w_prev: np.ndarray, w_today: np.ndarray) -> dict[str, Any]:
    changes = {
        k: {"from": float(a), "to": float(b)}
        for k, a, b in zip(keys, w_prev, w_today, strict=True)
        if not np.isclose(a, b)
    }
    return {"changes": changes}


def parametric_attribution(
    keys: list[str],
    w_prev: np.ndarray,
    w_today: np.ndarray,
    cov_prev: np.ndarray,
    cov_today: np.ndarray,
    confidence: float,
) -> list[Effect]:
    var_prev = normal_var_es(w_prev, cov_prev, confidence).var
    var_pos = normal_var_es(w_today, cov_prev, confidence).var

    vol_today, _ = cov_to_corr(cov_today)
    _, corr_prev = cov_to_corr(cov_prev)
    cov_vol_only = corr_to_cov(vol_today, corr_prev)
    var_vol = normal_var_es(w_today, cov_vol_only, confidence).var
    var_today = normal_var_es(w_today, cov_today, confidence).var

    vol_prev, _ = cov_to_corr(cov_prev)
    vol_moves = {
        k: {"from": float(a), "to": float(b)}
        for k, a, b in zip(keys, vol_prev, vol_today, strict=True)
    }
    return [
        Effect("position", var_pos - var_prev, _position_detail(keys, w_prev, w_today)),
        Effect("volatility", var_vol - var_pos, {"daily_vol": vol_moves}),
        Effect("correlation", var_today - var_vol, {}),
    ]


def historical_attribution(
    keys: list[str],
    w_prev: np.ndarray,
    w_today: np.ndarray,
    window_prev: pd.DataFrame,
    window_today: pd.DataFrame,
    confidence: float,
) -> list[Effect]:
    """Position effect, then the effect of the window rolling forward one day."""
    s_prev, s_today = window_prev.to_numpy(), window_today.to_numpy()
    var_prev = historical_var_es(s_prev, w_prev, confidence).var
    var_pos = historical_var_es(s_prev, w_today, confidence).var
    var_today = historical_var_es(s_today, w_today, confidence).var

    dropped = window_prev.index.difference(window_today.index)
    added = window_today.index.difference(window_prev.index)

    def scen(df: pd.DataFrame, dates: pd.Index) -> list[dict[str, Any]]:
        return [
            {
                "date": str(pd.Timestamp(d).date()),
                "pnl": float(df.loc[d].to_numpy() @ w_today),
                "in_tail": bool(df.loc[d].to_numpy() @ w_today <= -var_today),
            }
            for d in dates
        ]

    return [
        Effect("position", var_pos - var_prev, _position_detail(keys, w_prev, w_today)),
        Effect(
            "window_roll",
            var_today - var_pos,
            {"dropped": scen(window_prev, dropped), "added": scen(window_today, added)},
        ),
    ]


def generic_attribution(
    keys: list[str],
    var_prev: float,
    var_today: float,
    var_today_pos_prev_mkt: float,
    w_prev: np.ndarray,
    w_today: np.ndarray,
) -> list[Effect]:
    """For models without a finer split: position effect plus everything else as market data."""
    return [
        Effect(
            "position", var_today_pos_prev_mkt - var_prev, _position_detail(keys, w_prev, w_today)
        ),
        Effect("market_data", var_today - var_today_pos_prev_mkt, {}),
    ]
