"""Monte Carlo VaR with correlated normal returns (Cholesky)."""

from functools import lru_cache

import numpy as np

from riskcopilot.engine.tail import var_es_from_pnl
from riskcopilot.engine.types import VaRResult


@lru_cache(maxsize=4)
def _normals(n_paths: int, n: int, seed: int) -> np.ndarray:
    z = np.random.default_rng(seed).standard_normal((n_paths, n))
    z.flags.writeable = False
    return z


def simulate_returns(cov: np.ndarray, n_paths: int, seed: int) -> np.ndarray:
    """n_paths x n correlated zero-mean normal return vectors, r = L z.

    The same seed always gives the same draws, so runs are reproducible and auditable.
    """
    n = cov.shape[0]
    jitter = 1e-12 * np.trace(cov) / max(n, 1)
    chol = np.linalg.cholesky(cov + jitter * np.eye(n))
    return _normals(n_paths, n, seed) @ chol.T


def monte_carlo_var_es(
    w: np.ndarray, cov: np.ndarray, confidence: float, n_paths: int, seed: int
) -> tuple[VaRResult, np.ndarray]:
    """Returns the result and the simulated scenario returns (for decomposition)."""
    sims = simulate_returns(cov, n_paths, seed)
    return var_es_from_pnl(sims @ w, confidence), sims
