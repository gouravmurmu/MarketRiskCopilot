import json

import pytest
from fastapi.testclient import TestClient

from riskcopilot.api.deps import get_session
from riskcopilot.api.main import create_app
from riskcopilot.api.routes import copilot
from riskcopilot.config import Settings
from riskcopilot.db import models as m
from tests.agent.conftest import AS_OF, FakeClient, response


@pytest.fixture
def api(factory, monkeypatch):
    settings = Settings(anthropic_api_key=None)
    monkeypatch.setattr(copilot, "get_settings", lambda: settings)

    def session():
        with factory() as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = session
    with factory.begin() as s:
        s.query(m.Commentary).delete()
    return TestClient(app), settings


def test_commentary_404_then_approve(api, factory):
    client, _ = api
    assert client.get("/commentary").status_code == 404
    with factory.begin() as s:
        s.add(m.Commentary(as_of=AS_OF, draft_md="## Draft", status="needs_review"))
    body = client.get("/commentary").json()
    assert body["status"] == "needs_review" and body["draft_md"] == "## Draft"
    assert client.get("/commentary/dates").json()["items"][0]["as_of"] == str(AS_OF)
    r = client.post(
        "/commentary/approve",
        json={"as_of": str(AS_OF), "final_md": "## Final commentary text", "approved_by": "GM"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved" and r.json()["approved_by"] == "GM"


def test_approve_token_is_enforced_when_set(api, factory):
    client, settings = api
    settings.approve_token = "secret"
    with factory.begin() as s:
        s.add(m.Commentary(as_of=AS_OF, draft_md="## Draft", status="draft"))
    body = {"as_of": str(AS_OF), "final_md": "## Final commentary text", "approved_by": "GM"}
    assert client.post("/commentary/approve", json=body).status_code == 401
    ok = client.post("/commentary/approve", json=body, headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200


def test_generate_and_chat_need_configuration(api):
    client, _ = api
    assert client.post("/commentary/generate", json={}).status_code == 503
    chat = {"messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/chat", json=chat).status_code == 503


def test_chat_streams_server_sent_events(api, monkeypatch):
    client, settings = api
    settings.anthropic_api_key = "test-key"
    fake = FakeClient(
        [
            response("", [{"id": "t1", "name": "get_limit_status", "input": {}}]),
            response("All limits are ok."),
        ]
    )
    monkeypatch.setattr(copilot.llm, "make_client", lambda _: fake)
    r = client.post("/chat", json={"messages": [{"role": "user", "content": "Any breaches?"}]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert [e["type"] for e in events] == ["tool_call", "tool_result", "text", "done"]
