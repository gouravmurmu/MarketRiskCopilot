import json

import pytest

from riskcopilot.agent.chat import run_chat
from riskcopilot.agent.daily import gather, run_daily
from riskcopilot.agent.draft import Draft, output_schema, render_markdown
from riskcopilot.agent.tools import TOOLS, call_tool
from riskcopilot.agent.validator import validate
from riskcopilot.db import models as m
from tests.agent.conftest import AS_OF, FakeClient, response


def good_draft(outputs: dict) -> Draft:
    """A draft that copies its figures from the tool outputs, as the model should."""
    summary = outputs["get_risk_summary"]
    hs = next(f for f in summary["figures"] if f["model"] == "hs_500" and f["confidence"] == 0.99)
    attr = outputs['get_var_attribution({"model": "hs_500"})']
    limits = outputs["get_limit_status"]["items"]
    shown = [x for x in limits if x["status"] != "ok" or x["scope"] == "Portfolio"]
    bt = next(
        t
        for t in outputs["get_backtest_status"]["tests"]
        if t["model"] == "hs_500" and t["confidence"] == 0.99
    )
    chg = hs["change_pct"] * 100
    return Draft(
        headline=f"Portfolio 1-day 99% HS VaR moved {chg:+.1f}% to ${hs['var_usd'] / 1000:.1f}k.",
        var_summary=[
            {"metric": "HS 500d VaR 99% 1d", "value_usd": hs["var_usd"], "change_pct": chg},
            {"metric": "HS 500d ES 99% 1d", "value_usd": hs["es_usd"], "change_pct": None},
        ],
        drivers=[
            {
                "driver": e["effect"],
                "amount_usd": e["amount_usd"],
                "explanation": f"{e['effect']} effect of ${e['amount_usd'] / 1000:.1f}k.",
            }
            for e in attr["effects"]
        ],
        limits=[
            {
                "scope": x["scope"],
                "utilisation_pct": round(x["utilisation"] * 100, 1),
                "status": x["status"],
            }
            for x in shown
        ],
        backtesting=f"{bt['exceptions']} exceptions in {bt['T']} days; zone {bt['zone']}.",
        market_context="NVDA and SPY led the move.",
        data_caveats=[],
        sources=["get_risk_summary", "get_var_attribution", "get_limit_status"],
    )


def test_every_tool_answers_with_a_valid_schema(factory):
    with factory() as s:
        for tool in TOOLS:
            schema = tool.schema()
            assert schema["input_schema"]["type"] == "object"
            args = {"change_exposure": {"NVDA": -100_000}} if tool.name == "run_what_if" else {}
            ok, out = call_tool(s, tool.name, args)
            assert ok, (tool.name, out)
            json.dumps(out)


def test_tool_errors_are_returned_not_raised(factory):
    with factory() as s:
        assert call_tool(s, "get_risk_summary", {"as_of": "1999-01-04"})[0] is False
        assert call_tool(s, "get_top_contributors", {"model": "nope"})[0] is False
        assert call_tool(s, "get_market_moves", {"tickers": ["TSLA"]})[0] is False
        assert call_tool(s, "get_risk_summary", {"bogus": 1})[0] is False
        assert call_tool(s, "no_such_tool", {})[0] is False


def test_what_if_never_changes_positions(factory):
    with factory() as s:
        before = s.query(m.Position).count()
        ok, out = call_tool(s, "run_what_if", {"set_exposure": {"NVDA": 0}})
        assert ok and out["hypothetical"] and out["exposures_changed"]["NVDA"]["after"] == 0
        assert s.query(m.Position).count() == before


def test_validator_accepts_figures_copied_from_tools(factory):
    with factory() as s:
        outputs = gather(s, AS_OF)
    assert not any("error" in v for k, v in outputs.items() if isinstance(v, dict))
    rep = validate(good_draft(outputs), outputs)
    assert rep.ok, rep.errors
    assert rep.checked >= 8


def test_validator_rejects_invented_numbers_tickers_and_statuses(factory):
    with factory() as s:
        outputs = gather(s, AS_OF)
    d = good_draft(outputs)
    bad = Draft.model_validate(
        {
            **d.model_dump(),
            "headline": "VaR rose to $999.9k as TSLA fell 12.3%.",
            "limits": [{"scope": "Portfolio", "utilisation_pct": 55.5, "status": "breach"}],
        }
    )
    errors = " | ".join(validate(bad, outputs).errors)
    assert "$999.9k" in errors and "12.3%" in errors
    assert "TSLA" in errors
    assert "55.5" in errors and "says breach" in errors


def test_validator_requires_every_warning_to_be_reported(factory):
    with factory() as s:
        outputs = gather(s, AS_OF)
    outputs = json.loads(json.dumps(outputs))
    outputs["get_limit_status"]["items"][1]["status"] = "warning"
    scope = outputs["get_limit_status"]["items"][1]["scope"]
    d = good_draft(outputs).model_copy(update={"limits": []})
    assert any(scope in e and "not reported" in e for e in validate(d, outputs).errors)


def test_schema_is_closed_and_markdown_renders(factory):
    schema = output_schema()
    assert schema["additionalProperties"] is False
    assert all(v["additionalProperties"] is False for v in schema["$defs"].values())
    with factory() as s:
        md = render_markdown(good_draft(gather(s, AS_OF)), str(AS_OF))
    assert md.startswith(f"## Daily risk commentary, {AS_OF}")
    assert "| Portfolio |" in md and "_Sources:" in md


def test_daily_retries_with_validator_errors_then_stores_draft(factory, settings):
    with factory() as s:
        outputs = gather(s, AS_OF)
    good = good_draft(outputs)
    bad = good.model_copy(update={"headline": "VaR jumped 77.7% to $123.4k."})
    client = FakeClient([response(bad.model_dump_json()), response(good.model_dump_json())])
    res = run_daily(factory, AS_OF, client=client, settings=settings)
    assert res.status == "draft" and res.attempts == 2
    retry_msg = client.requests[1]["messages"][-1]["content"]
    assert "77.7%" in retry_msg
    req = client.requests[0]
    assert req["model"] == "claude-opus-5-5" and req["fallbacks"] == "default"
    assert req["output_config"]["format"]["type"] == "json_schema"
    with factory() as s:
        c = s.get(m.Commentary, AS_OF)
        assert c.status == "draft" and c.draft_md.startswith("## Daily risk commentary")
        assert c.validator_report["attempts"] == 2
        steps = s.query(m.AgentTrace).filter_by(trace_id=res.trace_id).count()
        assert steps == 11 + 2  # gathered tool outputs + two model calls


def test_daily_gives_up_after_two_retries(factory, settings):
    client = FakeClient([response("not json")] * 3)
    res = run_daily(factory, AS_OF, client=client, settings=settings)
    assert res.status == "needs_review" and res.attempts == 3
    with factory() as s:
        assert s.get(m.Commentary, AS_OF).status == "needs_review"


def test_daily_does_not_overwrite_approved_commentary(factory, settings):
    with factory.begin() as s:
        s.get(m.Commentary, AS_OF).status = "approved"
    res = run_daily(factory, AS_OF, client=FakeClient([]), settings=settings)
    assert res.status == "skipped"
    with factory.begin() as s:
        s.get(m.Commentary, AS_OF).status = "draft"


def test_chat_runs_tools_and_streams_the_answer(factory, settings):
    client = FakeClient(
        [
            response(
                "Checking.",
                [{"id": "t1", "name": "get_risk_summary", "input": {}}],
            ),
            response("VaR is $X. Sources: get_risk_summary"),
        ]
    )
    with factory() as s:
        events = list(
            run_chat(s, [{"role": "user", "content": "What is VaR?"}], client, settings, AS_OF)
        )
    kinds = [e["type"] for e in events]
    assert kinds == ["text", "tool_call", "tool_result", "text", "done"]
    assert events[2]["ok"] and events[-1]["tool_calls"] == 1
    second = client.requests[1]["messages"]
    assert second[2]["content"][0]["tool_use_id"] == "t1"  # list is shared, so index
    assert client.requests[0]["tools"][0]["eager_input_streaming"] is True


def test_chat_caps_tool_calls(factory, settings):
    settings.agent_max_tool_calls = 2
    loop = [
        response("", [{"id": f"t{i}", "name": "get_limit_status", "input": {}}]) for i in range(3)
    ]
    client = FakeClient([*loop, response("Done.")])
    with factory() as s:
        events = list(run_chat(s, [{"role": "user", "content": "Q"}], client, settings))
    results = [e for e in events if e["type"] == "tool_result"]
    assert [r["ok"] for r in results] == [True, True, False]
    assert events[-1]["type"] == "done"


@pytest.mark.parametrize("stop", ["refusal"])
def test_chat_reports_refusal(factory, settings, stop):
    client = FakeClient([response("", stop=stop)])
    with factory() as s:
        events = list(run_chat(s, [{"role": "user", "content": "Q"}], client, settings))
    assert events[-1]["type"] == "error"
