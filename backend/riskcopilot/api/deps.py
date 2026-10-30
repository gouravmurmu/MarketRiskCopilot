"""Shared API dependencies: database sessions and the as-of date resolver."""

from collections.abc import Iterator
from datetime import date
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from riskcopilot.config import get_settings
from riskcopilot.db import models as m
from riskcopilot.db.session import make_engine, make_session_factory


@lru_cache
def session_factory() -> sessionmaker[Session]:
    return make_session_factory(make_engine(get_settings().database_url))


def get_session() -> Iterator[Session]:
    with session_factory()() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def resolve_as_of(session: SessionDep, as_of: Annotated[date | None, Query()] = None) -> date:
    """The requested date, or the latest date with a completed risk run."""
    if as_of is not None:
        return as_of
    latest = session.scalar(select(func.max(m.RiskRun.as_of)))
    if latest is None:
        raise HTTPException(404, "No risk runs yet. Run the end-of-day job first.")
    return latest


AsOfDep = Annotated[date, Depends(resolve_as_of)]
