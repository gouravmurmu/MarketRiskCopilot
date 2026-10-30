"""Health, metadata and the protected EOD trigger."""

import secrets
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from sqlalchemy import func, select

from riskcopilot.api import schemas as s
from riskcopilot.api.deps import SessionDep, session_factory
from riskcopilot.config import get_settings
from riskcopilot.db import models as m
from riskcopilot.engine.runner import MODELS

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meta", response_model=s.Meta)
def meta(session: SessionDep) -> s.Meta:
    settings = get_settings()
    lo, hi = session.execute(select(func.min(m.RiskRun.as_of), func.max(m.RiskRun.as_of))).one()
    return s.Meta(
        latest_as_of=hi,
        first_as_of=lo,
        primary_model=settings.primary_model,
        primary_confidence=settings.primary_confidence,
        models=[
            s.ModelInfo(key=x.key, method=x.method, label=x.label, window=x.window) for x in MODELS
        ],
    )


def _run_eod() -> None:
    from riskcopilot.data.sources import Fred, YahooWithStooqFallback
    from riskcopilot.jobs.eod import run_eod

    settings = get_settings()
    run_eod(session_factory(), YahooWithStooqFallback(), Fred(settings.fred_api_key), settings)


@router.post("/jobs/eod", status_code=202)
def trigger_eod(
    background: BackgroundTasks, authorization: Annotated[str | None, Header()] = None
) -> dict[str, str]:
    token = get_settings().eod_token
    if not token:
        raise HTTPException(503, "EOD trigger is disabled (EOD_TOKEN not set)")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied, token):
        raise HTTPException(401, "Invalid token")
    background.add_task(_run_eod)
    return {"status": "accepted"}
