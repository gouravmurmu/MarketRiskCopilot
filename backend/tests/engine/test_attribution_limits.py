import numpy as np
import pandas as pd
import pytest

from riskcopilot.engine.attribution import historical_attribution, parametric_attribution
from riskcopilot.engine.covariance import ewma_cov
from riskcopilot.engine.historical import historical_var_es
from riskcopilot.engine.limits import check_limit
from riskcopilot.engine.parametric import normal_var_es
from riskcopilot.engine.runner import RunContext, attribute_change, run_models

KEYS = ["a", "b", "c"]


def _returns(n=600, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-01", periods=n)
    return pd.DataFrame(rng.standard_normal((n, 3)) * [0.01, 0.015, 0.02], index=idx, columns=KEYS)


def test_parametric_attribution_sums_to_change():
    r = _returns().to_numpy()
    w0, w1 = np.array([1e6, 5e5, 2e5]), np.array([1e6, 8e5, 2e5])
    c0, c1 = ewma_cov(r[:-1]), ewma_cov(r[1:] * 1.3)
    effects = parametric_attribution(KEYS, w0, w1, c0, c1, 0.99)
    change = normal_var_es(w1, c1, 0.99).var - normal_var_es(w0, c0, 0.99).var
    assert sum(e.amount for e in effects) == pytest.approx(change)
    assert effects[0].detail["changes"] == {"b": {"from": 5e5, "to": 8e5}}


def test_historical_attribution_sums_to_change():
    r = _returns()
    w0, w1 = np.array([1e6, 5e5, 2e5]), np.array([1e6, 5e5, 4e5])
    prev, today = r.iloc[-501:-1], r.iloc[-500:]
    effects = historical_attribution(KEYS, w0, w1, prev, today, 0.99)
    change = (
        historical_var_es(today.to_numpy(), w1, 0.99).var
        - historical_var_es(prev.to_numpy(), w0, 0.99).var
    )
    assert sum(e.amount for e in effects) == pytest.approx(change)
    roll = effects[1].detail
    assert len(roll["dropped"]) == 1 and len(roll["added"]) == 1


@pytest.mark.parametrize("model", ["hs_500", "pn_ewma", "mc_ewma", "fhs_500"])
def test_runner_attribution_reconciles(model):
    r = _returns()
    ctx = RunContext(mc_paths=5_000)
    e0 = {"a": 1e6, "b": 5e5, "c": 2e5}
    e1 = {"a": 1.2e6, "b": 5e5, "c": 2e5}
    effects = attribute_change(model, r.iloc[:-1], r, e0, e1, 0.99, ctx)
    acls = dict.fromkeys(KEYS, "Equity")
    v0 = next(x for x in run_models(r.iloc[:-1], e0, acls, ctx, (model,)) if x.confidence == 0.99)
    v1 = next(x for x in run_models(r, e1, acls, ctx, (model,)) if x.confidence == 0.99)
    assert sum(e.amount for e in effects) == pytest.approx(v1.var - v0.var, rel=1e-9, abs=1e-6)


@pytest.mark.parametrize(
    ("value", "status"),
    [(100, "ok"), (159.9, "ok"), (160, "warning"), (199, "warning"), (200, "breach")],
)
def test_limit_thresholds(value, status):
    assert check_limit("Portfolio", value, 200, 0.8).status == status
