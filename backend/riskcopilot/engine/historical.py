"""Historical simulation: plain, age-weighted and filtered (GARCH) variants."""

from dataclasses import dataclass

import numpy as np
from arch import arch_model

from riskcopilot.engine.tail import var_es_from_pnl
from riskcopilot.engine.types import VaRResult

AGE_LAMBDA = 0.98


def historical_var_es(scenarios: np.ndarray, w: np.ndarray, confidence: float) -> VaRResult:
    """Apply each historical return vector (rows) to today's exposures."""
    return var_es_from_pnl(scenarios @ w, confidence)


def age_weights(n: int, lam: float = AGE_LAMBDA) -> np.ndarray:
    """Boudoukh-Richardson-Whitelaw weights; the newest scenario (last row) weighs most."""
    ages = np.arange(n - 1, -1, -1)
    w = lam**ages * (1 - lam) / (1 - lam**n)
    return w


def age_weighted_var_es(
    scenarios: np.ndarray, w: np.ndarray, confidence: float, lam: float = AGE_LAMBDA
) -> VaRResult:
    return var_es_from_pnl(scenarios @ w, confidence, weights=age_weights(len(scenarios), lam))


@dataclass(frozen=True)
class GarchParams:
    omega: float
    alpha: float
    beta: float


def fit_garch(r: np.ndarray) -> GarchParams:
    """GARCH(1,1) on a single return series (scaled to percent for numerical stability)."""
    model = arch_model(r * 100.0, mean="Zero", vol="GARCH", p=1, q=1, rescale=False)
    res = model.fit(disp="off", show_warning=False)
    p = res.params
    return GarchParams(
        omega=float(p["omega"]) / 1e4, alpha=float(p["alpha[1]"]), beta=float(p["beta[1]"])
    )


def garch_filter(r: np.ndarray, params: GarchParams) -> tuple[np.ndarray, float]:
    """Conditional vol for each day in r and the one-step-ahead forecast."""
    var = np.empty(len(r) + 1)
    var[0] = r.var()
    for t in range(len(r)):
        var[t + 1] = params.omega + params.alpha * r[t] ** 2 + params.beta * var[t]
    vol = np.sqrt(var)
    return vol[:-1], float(vol[-1])


def filtered_scenarios(
    scenarios: np.ndarray, params: list[GarchParams] | None = None
) -> tuple[np.ndarray, list[GarchParams]]:
    """Rescale past returns by today's GARCH volatility: r* = r_t / sigma_t * sigma_{T+1}."""
    fitted = params or [fit_garch(scenarios[:, i]) for i in range(scenarios.shape[1])]
    out = np.empty_like(scenarios)
    for i, p in enumerate(fitted):
        vol, forecast = garch_filter(scenarios[:, i], p)
        safe = np.where(vol > 0, vol, forecast)
        out[:, i] = scenarios[:, i] / safe * forecast
    return out, fitted
