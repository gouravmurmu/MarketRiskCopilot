"""FastAPI app. Read-only over the risk tables, except what-if (computes, never stores),
the token-protected EOD and commentary triggers, commentary approval and the chat copilot.

    uvicorn riskcopilot.api.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from riskcopilot.api.routes import controls, copilot, meta, risk, whatif
from riskcopilot.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Market Risk Copilot API",
        version="0.3.0",
        description="Daily VaR/ES, attribution, backtests and limits for a sample portfolio.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    for r in (meta.router, risk.router, controls.router, whatif.router, copilot.router):
        app.include_router(r)
    return app


app = create_app()
