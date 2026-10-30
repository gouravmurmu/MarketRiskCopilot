import numpy as np
import pytest
from scipy import stats

from riskcopilot.engine.covariance import corr_to_cov, cov_to_corr, ewma_cov
from riskcopilot.engine.decomposition import parametric_components, simulation_components
from riskcopilot.engine.historical import age_weighted_var_es, age_weights
from riskcopilot.engine.montecarlo import monte_carlo_var_es
from riskcopilot.engine.parametric import normal_var_es, student_t_var_es
from riskcopilot.engine.tail import var_es_from_pnl

W = np.array([1_000_000.0, 500_000.0])
COV = np.array([[0.01**2, 0.5 * 0.01 * 0.02], [0.5 * 0.01 * 0.02, 0.02**2]])


def test_parametric_two_asset_closed_form():
    # sigma_p^2 = 1e6^2*1e-4 + 5e5^2*4e-4 + 2*1e6*5e5*1e-4 = 1e8 + 1e8 + 1e8
    sigma = np.sqrt(3e8)
    res = normal_var_es(W, COV, 0.99)
    assert res.var == pytest.approx(stats.norm.ppf(0.99) * sigma, rel=1e-12)
    assert res.es == pytest.approx(sigma * stats.norm.pdf(stats.norm.ppf(0.99)) / 0.01, rel=1e-12)


def test_historical_known_quantile():
    pnl = -np.arange(1, 501, dtype=float)[::-1]  # -500 .. -1, shuffled below
    np.random.default_rng(0).shuffle(pnl)
    res = var_es_from_pnl(pnl, 0.99)  # k = 5 worst: -500..-496
    assert res.var == 496
    assert res.es == pytest.approx(np.mean([500, 499, 498, 497, 496]))


def test_age_weighted_equals_plain_when_lambda_near_one():
    rng = np.random.default_rng(1)
    s = rng.standard_normal((500, 2)) * 0.01
    plain = var_es_from_pnl(s @ W, 0.99)
    aw = age_weighted_var_es(s, W, 0.99, lam=0.999999)
    assert aw.var == pytest.approx(plain.var, rel=1e-6)
    assert age_weights(500).sum() == pytest.approx(1.0)


def test_monte_carlo_converges_to_parametric():
    mc, _ = monte_carlo_var_es(W, COV, 0.99, n_paths=100_000, seed=11)
    assert mc.var == pytest.approx(normal_var_es(W, COV, 0.99).var, rel=0.02)


def test_monte_carlo_reproducible_with_seed():
    a, _ = monte_carlo_var_es(W, COV, 0.99, 20_000, seed=42)
    b, _ = monte_carlo_var_es(W, COV, 0.99, 20_000, seed=42)
    assert a == b


def test_student_t_fatter_than_normal_at_99():
    assert student_t_var_es(W, COV, 0.99, nu=4).var > normal_var_es(W, COV, 0.99).var


def test_parametric_components_sum_to_var():
    comps = parametric_components(["a", "b"], W, COV, 0.99)
    assert sum(c.component_var for c in comps) == pytest.approx(normal_var_es(W, COV, 0.99).var)


def test_simulation_components_sum_to_var():
    rng = np.random.default_rng(3)
    s = rng.standard_normal((500, 2)) @ np.linalg.cholesky(COV).T
    total = var_es_from_pnl(s @ W, 0.99).var
    comps = simulation_components(["a", "b"], W, s, 0.99, total)
    assert sum(c.component_var for c in comps) == pytest.approx(total)


def test_ewma_and_corr_roundtrip():
    rng = np.random.default_rng(4)
    r = rng.standard_normal((500, 3)) * 0.01
    cov = ewma_cov(r)
    vol, corr = cov_to_corr(cov)
    assert np.allclose(corr_to_cov(vol, corr), cov)
    assert np.allclose(np.diag(corr), 1.0)


def test_t_dof_fit_recovers_fat_tails():
    from riskcopilot.engine.parametric import fit_t_dof

    x = stats.t.rvs(4, size=5_000, random_state=1)
    assert fit_t_dof(x) == pytest.approx(4, abs=0.6)
