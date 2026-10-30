"""Run every VaR model for one date, plus decomposition, standalone asset-class VaR and
day-over-day attribution. Pure functions over a returns DataFrame: no database or network."""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from riskcopilot.engine import attribution as attr
from riskcopilot.engine.covariance import ewma_cov, sample_cov
from riskcopilot.engine.decomposition import (
    Contribution,
    parametric_components,
    roll_up,
    simulation_components,
)
from riskcopilot.engine.historical import (
    GarchParams,
    age_weighted_var_es,
    filtered_scenarios,
    historical_var_es,
)
from riskcopilot.engine.montecarlo import monte_carlo_var_es
from riskcopilot.engine.parametric import fit_t_dof, normal_var_es, student_t_var_es
from riskcopilot.engine.types import VaRResult

CONFIDENCES = (0.99, 0.975)
HORIZON_10D = float(np.sqrt(10))  # square-root-of-time; assumes i.i.d. returns


class InsufficientHistoryError(Exception):
    """The model cannot run on this date (e.g. the stress window is not fully in history)."""


@dataclass
class RunContext:
    mc_paths: int = 20_000
    mc_seed: int = 42
    stress_start: str = "2020-02-01"
    stress_end: str = "2021-01-31"
    # GARCH parameters are refitted at most once per calendar month (keyed "YYYY-MM").
    garch_cache: dict[str, list[GarchParams]] = field(default_factory=dict)
    # Student-t dof keyed by (as-of date, exposures), shared across confidence levels.
    nu_cache: dict[tuple[str, bytes], float] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelSpec:
    key: str
    method: str  # historical | parametric | monte_carlo | stressed
    label: str
    window: int


@dataclass
class ModelRun:
    model: str
    method: str
    label: str
    confidence: float
    window: int
    var: float
    es: float
    positions: list[Contribution]
    asset_classes: list[Contribution]

    @property
    def var_10d(self) -> float:
        return self.var * HORIZON_10D

    @property
    def es_10d(self) -> float:
        return self.es * HORIZON_10D


MODELS: tuple[ModelSpec, ...] = (
    ModelSpec("hs_250", "historical", "Historical simulation, 250d", 250),
    ModelSpec("hs_500", "historical", "Historical simulation, 500d", 500),
    ModelSpec("hs_aw_500", "historical", "Age-weighted HS (lambda 0.98), 500d", 500),
    ModelSpec("fhs_500", "historical", "Filtered HS (GARCH 1,1), 500d", 500),
    ModelSpec("pn_sample_500", "parametric", "Parametric normal, sample covariance", 500),
    ModelSpec("pn_ewma", "parametric", "Parametric normal, EWMA (lambda 0.94)", 500),
    ModelSpec("pt_ewma", "parametric", "Parametric Student-t, EWMA", 500),
    ModelSpec("mc_ewma", "monte_carlo", "Monte Carlo, EWMA covariance", 500),
    ModelSpec("svar", "stressed", "Stressed VaR (historical, 2020 stress window)", 250),
)
MODEL_BY_KEY = {m.key: m for m in MODELS}

Evaluator = Callable[
    [pd.DataFrame, np.ndarray, float, RunContext], tuple[VaRResult, list[Contribution]]
]


def _window(returns: pd.DataFrame, n: int) -> np.ndarray:
    return returns.iloc[-n:].to_numpy()


def _keys(returns: pd.DataFrame) -> list[str]:
    return [str(c) for c in returns.columns]


def _hs(n: int) -> Evaluator:
    def f(returns, w, conf, ctx):
        s = _window(returns, n)
        res = historical_var_es(s, w, conf)
        return res, simulation_components(_keys(returns), w, s, conf, res.var)

    return f


def _hs_aw(returns, w, conf, ctx):
    s = _window(returns, 500)
    res = age_weighted_var_es(s, w, conf)
    return res, simulation_components(_keys(returns), w, s, conf, res.var)


def _fhs(returns, w, conf, ctx):
    s = _window(returns, 500)
    month = str(returns.index[-1])[:7]
    params = ctx.garch_cache.get(month)
    filtered, fitted = filtered_scenarios(s, params)
    ctx.garch_cache[month] = fitted
    res = historical_var_es(filtered, w, conf)
    return res, simulation_components(_keys(returns), w, filtered, conf, res.var)


def _pn(cov_fn: Callable[[np.ndarray], np.ndarray]) -> Evaluator:
    def f(returns, w, conf, ctx):
        cov = cov_fn(_window(returns, 500))
        return normal_var_es(w, cov, conf), parametric_components(_keys(returns), w, cov, conf)

    return f


def _pt(returns, w, conf, ctx):
    s = _window(returns, 500)
    cov = ewma_cov(s)
    key = (str(returns.index[-1]), w.tobytes())
    if key not in ctx.nu_cache:
        ctx.nu_cache[key] = fit_t_dof(s @ w)
    nu = ctx.nu_cache[key]
    res = student_t_var_es(w, cov, conf, nu)
    normal = normal_var_es(w, cov, conf).var
    scale = res.var / normal if normal else 1.0
    comps = [
        Contribution(c.key, c.exposure, c.component_var * scale, c.marginal_var * scale)
        for c in parametric_components(_keys(returns), w, cov, conf)
    ]
    return res, comps


def _mc(returns, w, conf, ctx):
    cov = ewma_cov(_window(returns, 500))
    res, sims = monte_carlo_var_es(w, cov, conf, ctx.mc_paths, ctx.mc_seed)
    return res, simulation_components(_keys(returns), w, sims, conf, res.var)


def _svar(returns, w, conf, ctx):
    if returns.index[-1] < pd.Timestamp(ctx.stress_end):
        raise InsufficientHistoryError("stress window not yet complete")
    s = returns.loc[ctx.stress_start : ctx.stress_end].to_numpy()
    if len(s) < 100:
        raise InsufficientHistoryError("stress window missing from history")
    res = historical_var_es(s, w, conf)
    return res, simulation_components(_keys(returns), w, s, conf, res.var)


EVALUATORS: dict[str, Evaluator] = {
    "hs_250": _hs(250),
    "hs_500": _hs(500),
    "hs_aw_500": _hs_aw,
    "fhs_500": _fhs,
    "pn_sample_500": _pn(sample_cov),
    "pn_ewma": _pn(ewma_cov),
    "pt_ewma": _pt,
    "mc_ewma": _mc,
    "svar": _svar,
}


def evaluate(
    model: str, returns: pd.DataFrame, exposures: dict[str, float], conf: float, ctx: RunContext
) -> VaRResult:
    w = np.array([exposures.get(c, 0.0) for c in returns.columns])
    return EVALUATORS[model](returns, w, conf, ctx)[0]


def run_models(
    returns: pd.DataFrame,
    exposures: dict[str, float],
    asset_class_of: dict[str, str],
    ctx: RunContext,
    models: tuple[str, ...] | None = None,
    confidences: tuple[float, ...] = CONFIDENCES,
) -> list[ModelRun]:
    """returns: history up to and including the as-of date (rows = dates, cols = tickers)."""
    w = np.array([exposures.get(c, 0.0) for c in returns.columns])
    out = []
    for key in models or tuple(EVALUATORS):
        spec = MODEL_BY_KEY[key]
        for conf in confidences:
            try:
                res, comps = EVALUATORS[key](returns, w, conf, ctx)
            except InsufficientHistoryError:
                continue
            out.append(
                ModelRun(
                    model=key,
                    method=spec.method,
                    label=spec.label,
                    confidence=conf,
                    window=spec.window,
                    var=res.var,
                    es=res.es,
                    positions=comps,
                    asset_classes=roll_up(comps, asset_class_of),
                )
            )
    return out


def standalone_by_asset_class(
    model: str,
    returns: pd.DataFrame,
    exposures: dict[str, float],
    asset_class_of: dict[str, str],
    conf: float,
    ctx: RunContext,
) -> dict[str, float]:
    """Standalone VaR of each asset-class sub-portfolio (what the limits are set on)."""
    out: dict[str, float] = {}
    for ac in sorted(set(asset_class_of.values())):
        sub = {k: v for k, v in exposures.items() if asset_class_of.get(k) == ac}
        out[ac] = evaluate(model, returns, sub, conf, ctx).var
    out["Portfolio"] = evaluate(model, returns, exposures, conf, ctx).var
    return out


def attribute_change(
    model: str,
    returns_prev: pd.DataFrame,
    returns_today: pd.DataFrame,
    exposures_prev: dict[str, float],
    exposures_today: dict[str, float],
    conf: float,
    ctx: RunContext,
) -> list[attr.Effect]:
    """Split VaR(today) - VaR(yesterday) into effects that sum exactly to the change."""
    keys = _keys(returns_today)
    w0 = np.array([exposures_prev.get(c, 0.0) for c in keys])
    w1 = np.array([exposures_today.get(c, 0.0) for c in keys])
    spec = MODEL_BY_KEY[model]
    if model in ("hs_250", "hs_500"):
        return attr.historical_attribution(
            keys,
            w0,
            w1,
            returns_prev.iloc[-spec.window :],
            returns_today.iloc[-spec.window :],
            conf,
        )
    if model in ("pn_sample_500", "pn_ewma"):
        cov_fn = sample_cov if model == "pn_sample_500" else ewma_cov
        return attr.parametric_attribution(
            keys,
            w0,
            w1,
            cov_fn(_window(returns_prev, 500)),
            cov_fn(_window(returns_today, 500)),
            conf,
        )
    try:
        var_prev = evaluate(model, returns_prev, exposures_prev, conf, ctx).var
    except InsufficientHistoryError:
        return []
    var_mid = evaluate(model, returns_prev, exposures_today, conf, ctx).var
    var_today = evaluate(model, returns_today, exposures_today, conf, ctx).var
    return attr.generic_attribution(keys, var_prev, var_today, var_mid, w0, w1)
