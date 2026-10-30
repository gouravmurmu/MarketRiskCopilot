"""Covariance estimators: equally weighted sample and RiskMetrics EWMA."""

import numpy as np

EWMA_LAMBDA = 0.94


def sample_cov(returns: np.ndarray) -> np.ndarray:
    return np.atleast_2d(np.cov(returns, rowvar=False, ddof=1))


def ewma_cov(returns: np.ndarray, lam: float = EWMA_LAMBDA) -> np.ndarray:
    """Zero-mean EWMA covariance; the newest observation (last row) gets the largest weight."""
    r = np.asarray(returns, dtype=float)
    n = r.shape[0]
    w = (1 - lam) * lam ** np.arange(n - 1, -1, -1)
    w = w / w.sum()
    return np.atleast_2d((r * w[:, None]).T @ r)


def cov_to_corr(cov: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    vol = np.sqrt(np.diag(cov))
    safe = np.where(vol > 0, vol, 1.0)
    corr = cov / np.outer(safe, safe)
    return vol, corr


def corr_to_cov(vol: np.ndarray, corr: np.ndarray) -> np.ndarray:
    return corr * np.outer(vol, vol)
