import numpy as np
import pytest

from riskcopilot.engine.backtest import christoffersen_ind, kupiec_pof, run_backtest, traffic_light


def test_kupiec_textbook():
    # T=250, x=8 at 1%, worked by hand:
    # ln L0 = 242 ln 0.99 + 8 ln 0.01 = -39.2735; ln L1 = 242 ln 0.968 + 8 ln 0.032 = -35.4067
    lr, p = kupiec_pof(250, 8, 0.01)
    assert lr == pytest.approx(7.7336, abs=1e-3)
    assert lr > 3.84 and p < 0.01


def test_kupiec_zero_exceptions_finite():
    lr, p = kupiec_pof(250, 0, 0.01)
    assert lr == pytest.approx(-2 * 250 * np.log(0.99))
    assert np.isfinite(p)


def test_christoffersen_no_clustering_vs_clustering():
    spread = np.zeros(250, dtype=int)
    spread[[20, 80, 140, 200]] = 1
    clustered = np.zeros(250, dtype=int)
    clustered[[100, 101, 102, 103]] = 1
    lr_spread, _ = christoffersen_ind(spread)
    lr_clustered, p_clustered = christoffersen_ind(clustered)
    assert lr_spread < 1.0
    assert lr_clustered > 3.84 and p_clustered < 0.05


def test_christoffersen_no_exceptions():
    lr, p = christoffersen_ind(np.zeros(250, dtype=int))
    assert lr == 0.0 and p == 1.0


@pytest.mark.parametrize(
    ("x", "zone"), [(0, "green"), (4, "green"), (5, "yellow"), (9, "yellow"), (10, "red")]
)
def test_basel_traffic_light(x, zone):
    assert traffic_light(250, x) == zone


def test_run_backtest_counts_exceptions():
    var = np.full(250, 100.0)
    pnl = np.zeros(250)
    pnl[[10, 50, 90]] = -150.0
    res = run_backtest(var, pnl, 0.99)
    assert res.exceptions == 3 and res.zone == "green"
    assert res.lr_cc == pytest.approx(res.lr_pof + res.lr_ind)
