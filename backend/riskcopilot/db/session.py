from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str) -> Engine:
    # Neon and Supabase hand out postgres(ql):// URLs; SQLAlchemy wants an explicit driver.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        # Enforce foreign keys like Postgres does, so local runs and tests catch ordering bugs.
        @event.listens_for(engine, "connect")
        def _fk_on(conn: Any, _: Any) -> None:
            conn.execute("PRAGMA foreign_keys=ON")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
