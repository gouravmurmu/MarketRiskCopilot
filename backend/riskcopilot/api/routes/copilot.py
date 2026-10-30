"""AI copilot: daily commentary (read, generate, approve) and the streaming chat."""

import json
import secrets
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from riskcopilot.agent import llm
from riskcopilot.agent.chat import run_chat
from riskcopilot.api import schemas as s
from riskcopilot.api.deps import SessionDep, resolve_as_of, session_factory
from riskcopilot.config import get_settings
from riskcopilot.db import models as m

router = APIRouter(tags=["copilot"])


def _check_token(expected: str | None, authorization: str | None, what: str) -> None:
    if not expected:
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, f"Invalid {what} token")


def _require_llm() -> None:
    if not get_settings().anthropic_api_key:
        raise HTTPException(503, "The copilot is disabled (ANTHROPIC_API_KEY not set)")


def _out(c: m.Commentary) -> s.CommentaryOut:
    return s.CommentaryOut.model_validate(c, from_attributes=True)


@router.get("/commentary", response_model=s.CommentaryOut)
def commentary(
    session: SessionDep, as_of: Annotated[date | None, Query()] = None
) -> s.CommentaryOut:
    if as_of is None:
        as_of = session.scalar(select(func.max(m.Commentary.as_of)))
    c = session.get(m.Commentary, as_of) if as_of else None
    if c is None:
        raise HTTPException(404, "No commentary yet")
    return _out(c)


@router.get("/commentary/dates", response_model=s.CommentaryDates)
def commentary_dates(session: SessionDep) -> s.CommentaryDates:
    rows = session.execute(
        select(m.Commentary.as_of, m.Commentary.status).order_by(m.Commentary.as_of.desc())
    ).all()
    return s.CommentaryDates(items=[{"as_of": d, "status": st} for d, st in rows[:60]])


def _generate(as_of: date | None, force: bool) -> None:
    from riskcopilot.agent.daily import run_daily

    run_daily(session_factory(), as_of, force=force)


@router.post("/commentary/generate", status_code=202)
def generate(
    req: s.GenerateRequest,
    background: BackgroundTasks,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Draft the commentary in the background. Protected by EOD_TOKEN because it costs money."""
    settings = get_settings()
    if not settings.eod_token:
        raise HTTPException(503, "Generation is disabled (EOD_TOKEN not set)")
    _check_token(settings.eod_token, authorization, "EOD")
    _require_llm()
    background.add_task(_generate, req.as_of, req.force)
    return {"status": "accepted"}


@router.post("/commentary/approve", response_model=s.CommentaryOut)
def approve(
    session: SessionDep,
    req: s.ApproveRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> s.CommentaryOut:
    _check_token(get_settings().approve_token, authorization, "approver")
    c = session.get(m.Commentary, req.as_of)
    if c is None:
        raise HTTPException(404, f"No commentary on {req.as_of}")
    c.final_md = req.final_md
    c.status = "approved"
    c.approved_by = req.approved_by
    c.approved_at = datetime.now(UTC).replace(tzinfo=None)
    session.commit()
    return _out(c)


def _sse(events: Iterator[dict[str, Any]]) -> Iterator[str]:
    for e in events:
        yield f"data: {json.dumps(e, default=str)}\n\n"


@router.post("/chat")
def chat(session: SessionDep, req: s.ChatRequest) -> StreamingResponse:
    """Streams server-sent events; see riskcopilot.agent.chat for the event shapes."""
    _require_llm()
    settings = get_settings()
    today = datetime.now(UTC).date()
    used = session.scalar(
        select(func.count(func.distinct(m.AgentTrace.trace_id))).where(
            m.AgentTrace.mode == "chat", func.date(m.AgentTrace.created_at) == today
        )
    )
    if (used or 0) >= settings.chat_daily_limit:
        raise HTTPException(429, "Daily question limit reached; try again tomorrow")
    as_of = resolve_as_of(session, req.as_of)
    client = llm.make_client(settings)
    history = [x.model_dump() for x in req.messages]
    bind = session.get_bind()

    def events() -> Iterator[dict[str, Any]]:
        with Session(bind) as own:  # the request session closes before streaming ends
            try:
                yield from run_chat(own, history, client, settings, as_of)
            except Exception as e:  # surface API errors to the UI instead of a broken stream
                yield {"type": "error", "message": f"Copilot error: {type(e).__name__}"}
            finally:
                own.commit()

    return StreamingResponse(
        _sse(events()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
