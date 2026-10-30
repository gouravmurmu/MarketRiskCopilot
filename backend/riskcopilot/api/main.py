"""FastAPI app. Read-only over the risk tables, except what-if (computes, never stores)
and the token-protected EOD trigger.

    uvicorn riskcopilot.api.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from riskcopilot.api.routes import controls, meta, risk, whatif
from riskcopilot.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Market Risk Copilot API",
        version="0.2.0",
        description="Daily VaR/ES, attribution, backtests and limits for a sample portfolio.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    for r in (meta.router, risk.router, controls.router, whatif.router):
        app.include_router(r)
    return app


app = create_app()
