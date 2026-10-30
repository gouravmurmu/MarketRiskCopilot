"""VaR backtests: Kupiec POF, Christoffersen independence, conditional coverage, Basel zones."""

from dataclasses import dataclass

import numpy as np
from scipy import stats
from scipy.special import xlogy


@dataclass(frozen=True)
class BacktestResult:
    T: int
    exceptions: int
    expected: float
    lr_pof: float
    p_pof: float
    lr_ind: float
    p_ind: float
    lr_cc: float
    p_cc: float
    zone: str


def _loglik(n_fail: float, n_ok: float, p: float) -> float:
    # xlogy gives the 0 * ln(0) = 0 convention, so the statistics stay finite.
    return float(xlogy(n_ok, 1 - p) + xlogy(n_fail, p))


def kupiec_pof(T: int, x: int, p: float) -> tuple[float, float]:
    """LR_POF ~ chi2(1). p = expected exception rate (1 - confidence)."""
    phat = x / T
    lr = -2 * (_loglik(x, T - x, p) - _loglik(x, T - x, phat))
    lr = max(lr, 0.0)
    return lr, float(stats.chi2.sf(lr, 1))


def christoffersen_ind(exceptions: np.ndarray) -> tuple[float, float]:
    """LR_ind ~ chi2(1), from first-order transition counts of the exception series."""
    e = np.asarray(exceptions, dtype=int)
    prev, curr = e[:-1], e[1:]
    n00 = int(((prev == 0) & (curr == 0)).sum())
    n01 = int(((prev == 0) & (curr == 1)).sum())
    n10 = int(((prev == 1) & (curr == 0)).sum())
    n11 = int(((prev == 1) & (curr == 1)).sum())
    pi01 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi11 = n11 / (n10 + n11) if n10 + n11 else 0.0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11) if len(prev) else 0.0
    l0 = _loglik(n01 + n11, n00 + n10, pi)
    l1 = _loglik(n01, n00, pi01) + _loglik(n11, n10, pi11)
    lr = max(-2 * (l0 - l1), 0.0)
    return lr, float(stats.chi2.sf(lr, 1))


def traffic_light(T: int, x: int, p: float = 0.01) -> str:
    """Basel zones from the binomial CDF: green below 95%, red at or above 99.99%.

    For T = 250 and p = 1% this gives green 0-4, yellow 5-9, red 10+.
    """
    cdf = stats.binom.cdf(x, T, p)
    if cdf < 0.95:
        return "green"
    if cdf < 0.9999:
        return "yellow"
    return "red"


def run_backtest(var: np.ndarray, realised_pnl: np.ndarray, confidence: float) -> BacktestResult:
    """var[t] is the forecast for the loss on realised_pnl[t] (already aligned by the caller)."""
    var = np.asarray(var, dtype=float)
    pnl = np.asarray(realised_pnl, dtype=float)
    exc = (-pnl > var).astype(int)
    T, x, p = len(exc), int(exc.sum()), 1 - confidence
    lr_pof, p_pof = kupiec_pof(T, x, p)
    lr_ind, p_ind = christoffersen_ind(exc)
    lr_cc = lr_pof + lr_ind
    return BacktestResult(
        T=T,
        exceptions=x,
        expected=T * p,
        lr_pof=lr_pof,
        p_pof=p_pof,
        lr_ind=lr_ind,
        p_ind=p_ind,
        lr_cc=lr_cc,
        p_cc=float(stats.chi2.sf(lr_cc, 2)),
        zone=traffic_light(T, x, p),
    )
