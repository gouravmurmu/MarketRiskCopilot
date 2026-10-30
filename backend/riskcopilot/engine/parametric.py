"""Parametric (variance-covariance) VaR and ES: normal and Student-t."""

import numpy as np
from scipy import optimize, stats

from riskcopilot.engine.types import VaRResult


def portfolio_sigma(w: np.ndarray, cov: np.ndarray) -> float:
    return float(np.sqrt(w @ cov @ w))


def normal_var_es(w: np.ndarray, cov: np.ndarray, confidence: float) -> VaRResult:
    sigma = portfolio_sigma(w, cov)
    z = stats.norm.ppf(confidence)
    return VaRResult(var=z * sigma, es=sigma * stats.norm.pdf(z) / (1 - confidence))


def fit_t_dof(pnl: np.ndarray, floor: float = 2.5, cap: float = 100.0) -> float:
    """MLE of Student-t degrees of freedom for P&L standardised to unit variance.

    The t is scaled to unit variance for every nu, so this is a 1-D bounded search.
    """
    x = np.asarray(pnl, dtype=float)
    x = (x - x.mean()) / x.std(ddof=1)

    def nll(nu: float) -> float:
        s = np.sqrt((nu - 2) / nu)
        return float(-(stats.t.logpdf(x / s, nu) - np.log(s)).sum())

    res = optimize.minimize_scalar(nll, bounds=(floor, cap), method="bounded")
    return float(res.x)


def student_t_var_es(w: np.ndarray, cov: np.ndarray, confidence: float, nu: float) -> VaRResult:
    """Student-t scaled to the portfolio variance, so fat tails come only from nu."""
    sigma = portfolio_sigma(w, cov)
    scale = sigma * np.sqrt((nu - 2) / nu)
    q = stats.t.ppf(confidence, nu)
    es_std = stats.t.pdf(q, nu) * (nu + q**2) / ((nu - 1) * (1 - confidence))
    return VaRResult(var=float(scale * q), es=float(scale * es_std))
