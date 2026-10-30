"""Chat copilot: a tool-use loop that streams events for the UI.

Events (dicts, sent as server-sent events by the API):
    {"type": "tool_call", "id", "name", "input"}
    {"type": "tool_result", "id", "name", "ok", "preview"}
    {"type": "text", "text"}        a chunk of the answer
    {"type": "done", "trace_id", "tool_calls"}
    {"type": "error", "message"}
"""

import time
from collections.abc import Iterator
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from riskcopilot.agent import llm
from riskcopilot.agent.tools import TOOLS, call_tool, dumps
from riskcopilot.config import Settings

MAX_TURNS = 12  # model calls per question, a backstop above the tool-call limit


def _history(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Text-only history from the UI; tool steps of earlier questions are not replayed."""
    out = [
        {"role": x["role"], "content": x["content"]}
        for x in messages
        if x.get("role") in ("user", "assistant") and x.get("content")
    ]
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def run_chat(
    session: Session,
    messages: list[dict[str, str]],
    client: Any,
    settings: Settings,
    as_of: date | None = None,
) -> Iterator[dict[str, Any]]:
    tracer = llm.Tracer(session, "chat", as_of)
    convo = _history(messages)
    if not convo or convo[-1]["role"] != "user":
        yield {"type": "error", "message": "The last message must be a question"}
        return
    system = llm.CHAT_SYSTEM
    if as_of:
        system += f"\n\nThe analyst is looking at business date {as_of.isoformat()}."
    tools = [t.schema(eager=True) for t in TOOLS]
    calls = 0
    for _ in range(MAX_TURNS):
        t0 = time.perf_counter()
        with client.beta.messages.stream(
            **llm.request_kwargs(settings),
            max_tokens=8000,
            system=system,
            tools=tools,
            messages=convo,
            output_config={"effort": settings.agent_effort},
        ) as stream:
            for event in stream:
                if event.type == "text":
                    yield {"type": "text", "text": event.text}
            resp = stream.get_final_message()
        tracer.log(
            output=llm.text_of(resp),
            tokens=llm.usage_tokens(resp),
            started=t0,
            model=getattr(resp, "model", settings.agent_model),
        )
        if resp.stop_reason == "refusal":
            yield {"type": "error", "message": "The copilot declined to answer that question."}
            return
        convo.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "pause_turn":
            continue
        uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if resp.stop_reason == "max_tokens" and uses:
            yield {"type": "error", "message": "The answer was cut off. Try a narrower question."}
            return
        if not uses:
            break
        results = []
        for b in uses:
            calls += 1
            yield {"type": "tool_call", "id": b.id, "name": b.name, "input": b.input}
            if calls > settings.agent_max_tool_calls:
                ok, out = (
                    False,
                    (
                        f"Tool call limit ({settings.agent_max_tool_calls}) reached. "
                        "Answer now with the evidence you already have."
                    ),
                )
            elif not isinstance(b.input, dict):
                ok, out = False, "Input must be a JSON object"
            else:
                t1 = time.perf_counter()
                ok, out = call_tool(session, b.name, b.input)
                text = dumps(out)
                tracer.log(tool=b.name, args=b.input, output=text, started=t1)
            payload = dumps(out) if ok else str(out)
            yield {
                "type": "tool_result",
                "id": b.id,
                "name": b.name,
                "ok": ok,
                "preview": payload[:300],
            }
            results.append(
                {"type": "tool_result", "tool_use_id": b.id, "content": payload, "is_error": not ok}
            )
        convo.append({"role": "user", "content": results})
    else:
        yield {"type": "error", "message": "Stopped after too many steps."}
        return
    yield {"type": "done", "trace_id": tracer.trace_id, "tool_calls": calls}
