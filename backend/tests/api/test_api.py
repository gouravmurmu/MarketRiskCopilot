from datetime import date

import pytest
from fastapi.testclient import TestClient

from riskcopilot.api.deps import get_session
from riskcopilot.api.main import create_app
from riskcopilot.config import Settings
from riskcopilot.db import models as m
from riskcopilot.db.session import make_engine, make_session_factory
from riskcopilot.jobs.eod import run_eod
from tests.conftest import FakePrices, synthetic_prices

AS_OF = date(2020, 1, 31)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    engine = make_engine(f"sqlite:///{tmp_path_factory.mktemp('api') / 'api.db'}")
    m.Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    settings = Settings(history_start="2018-01-01", mc_paths=2_000)
    res = run_eod(factory, FakePrices(synthetic_prices()), None, settings, AS_OF)
    assert res.status == "ok"

    def session():
        with factory() as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = session
    return TestClient(app)


def test_meta_and_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    meta = client.get("/meta").json()
    assert meta["latest_as_of"] == str(AS_OF)
    assert len(meta["models"]) == 9


def test_summary_has_change_vs_previous_day(client):
    body = client.get("/risk/summary").json()
    assert body["as_of"] == str(AS_OF)
    hs = next(f for f in body["figures"] if f["model"] == "hs_500" and f["confidence"] == 0.99)
    assert hs["var_usd"] > 0 and hs["es_usd"] >= hs["var_usd"]
    assert hs["change_usd"] == pytest.approx(hs["var_usd"] - hs["prev_var_usd"])


def test_attribution_reconciles(client):
    body = client.get("/risk/attribution", params={"model": "pn_ewma"}).json()
    total = sum(e["amount_usd"] for e in body["effects"])
    assert total == pytest.approx(body["var_usd"] - body["previous_var_usd"])
    assert [e["effect"] for e in body["effects"]] == ["position", "volatility", "correlation"]


def test_contributors_sum_to_total(client):
    body = client.get("/risk/contributors", params={"level": "asset_class"}).json()
    assert sum(i["component_var"] for i in body["items"]) == pytest.approx(body["total_var_usd"])


def test_history_has_pnl_and_exceptions(client):
    pts = client.get("/risk/history").json()["points"]
    assert len(pts) > 20
    assert pts[0]["pnl_usd"] is not None and isinstance(pts[0]["exception"], bool)
    assert pts[-1]["pnl_usd"] is None  # no next day yet for the latest date


def test_limits_portfolio_backtest_dq(client):
    limits = client.get("/limits").json()["items"]
    assert [x["scope"] for x in limits][0] == "Portfolio" and len(limits) == 6
    port = client.get("/portfolio").json()
    assert port["total_usd"] == pytest.approx(10_000_000)
    bt = client.get("/backtest", params={"model": "hs_500", "scope": "full"}).json()
    assert {b["confidence"] for b in bt} == {0.99, 0.975}
    dq = client.get("/data-quality").json()
    assert dq["blocking"] is False and "SPY" in dq["latest_price_dates"]


def test_whatif_cut_position_lowers_var(client):
    body = client.post(
        "/whatif", json={"set_exposure": {"QQQ": 500_000}, "models": ["hs_500"]}
    ).json()
    fig = next(f for f in body["figures"] if f["confidence"] == 0.99)
    assert fig["var_after"] < fig["var_before"]
    eq_before = next(x for x in body["limits_before"] if x["scope"] == "Equity")
    eq_after = next(x for x in body["limits_after"] if x["scope"] == "Equity")
    assert eq_after["value_usd"] < eq_before["value_usd"]


def test_whatif_rejects_unknown_ticker(client):
    assert client.post("/whatif", json={"set_exposure": {"TSLA": 1}}).status_code == 422


def test_unknown_model_rejected(client):
    assert client.get("/risk/history", params={"model": "nope"}).status_code == 422


def test_eod_trigger_disabled_without_token(client):
    assert client.post("/jobs/eod").status_code == 503
