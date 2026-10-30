"""Empirical VaR / ES from a vector of P&L scenarios."""

import math

import numpy as np

from riskcopilot.engine.types import VaRResult


def tail_count(n: int, confidence: float) -> int:
    """Number of scenarios in the tail: ceil(n * (1 - confidence)), at least 1."""
    return max(1, math.ceil(round(n * (1.0 - confidence), 9)))


def var_es_from_pnl(
    pnl: np.ndarray, confidence: float, weights: np.ndarray | None = None
) -> VaRResult:
    """VaR = -q_{1-a}(dP); ES = average loss of the scenarios at or beyond VaR.

    Unweighted: VaR is the k-th worst P&L with k = ceil(n(1-a)), ES the mean of the k worst.
    Weighted (age-weighted HS): walk the sorted scenarios until the cumulative weight reaches
    1-a; ES is the weight-averaged loss of that tail.
    """
    pnl = np.asarray(pnl, dtype=float)
    order = np.argsort(pnl, kind="stable")
    sorted_pnl = pnl[order]
    if weights is None:
        k = tail_count(len(pnl), confidence)
        return VaRResult(var=float(-sorted_pnl[k - 1]), es=float(-sorted_pnl[:k].mean()))

    w = np.asarray(weights, dtype=float)[order]
    w = w / w.sum()
    cum = np.cumsum(w)
    k = int(np.searchsorted(cum, 1.0 - confidence - 1e-12)) + 1
    k = min(k, len(pnl))
    tail_w = w[:k]
    es = float(-(sorted_pnl[:k] * tail_w).sum() / tail_w.sum())
    return VaRResult(var=float(-sorted_pnl[k - 1]), es=es)
