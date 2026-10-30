"""Component and marginal VaR (Euler allocation)."""

from dataclasses import dataclass

import numpy as np
from scipy import stats

from riskcopilot.engine.tail import tail_count


@dataclass(frozen=True)
class Contribution:
    key: str
    exposure: float
    component_var: float
    marginal_var: float  # dVaR / d(exposure): VaR change per extra $1


def parametric_components(
    keys: list[str], w: np.ndarray, cov: np.ndarray, confidence: float
) -> list[Contribution]:
    """CVaR_i = z * w_i (Sigma w)_i / sigma_p; components sum to total normal VaR."""
    z = stats.norm.ppf(confidence)
    sigma = float(np.sqrt(w @ cov @ w))
    marginal = z * (cov @ w) / sigma
    return [
        Contribution(k, float(w[i]), float(w[i] * marginal[i]), float(marginal[i]))
        for i, k in enumerate(keys)
    ]


def simulation_components(
    keys: list[str],
    w: np.ndarray,
    scenarios: np.ndarray,
    confidence: float,
    total_var: float,
    half_window: int | None = None,
) -> list[Contribution]:
    """Kernel estimate for simulation VaR.

    Each position's component is minus its average P&L in the scenarios around the VaR
    quantile. The raw kernel components are rescaled so they sum exactly to total VaR.
    """
    pnl = scenarios @ w
    order = np.argsort(pnl, kind="stable")
    k = tail_count(len(pnl), confidence)
    h = half_window if half_window is not None else max(2, int(0.0025 * len(pnl)))
    lo, hi = max(0, k - 1 - h), min(len(pnl), k + h)
    idx = order[lo:hi]
    raw = -(scenarios[idx] * w).mean(axis=0)
    total_raw = raw.sum()
    comp = raw * (total_var / total_raw) if abs(total_raw) > 1e-12 else raw
    marginal = np.divide(comp, w, out=np.zeros_like(comp), where=w != 0)
    return [
        Contribution(k_, float(w[i]), float(comp[i]), float(marginal[i]))
        for i, k_ in enumerate(keys)
    ]


def roll_up(contribs: list[Contribution], group_of: dict[str, str]) -> list[Contribution]:
    """Sum position components by group (e.g. asset class)."""
    groups: dict[str, list[Contribution]] = {}
    for c in contribs:
        groups.setdefault(group_of[c.key], []).append(c)
    out = []
    for g, cs in groups.items():
        exposure = sum(c.exposure for c in cs)
        comp = sum(c.component_var for c in cs)
        out.append(Contribution(g, exposure, comp, comp / exposure if exposure else 0.0))
    return out
