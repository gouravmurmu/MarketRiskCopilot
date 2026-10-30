"""What-if: VaR, ES and limit use after hypothetical exposure changes.

Uses the same engine functions as the daily batch on the stored returns, so a what-if
answer is consistent with the reported numbers.
"""

from fastapi import APIRouter, HTTPException

from riskcopilot import reference
from riskcopilot.api import schemas as s
from riskcopilot.api.deps import SessionDep, resolve_as_of
from riskcopilot.config import get_settings
from riskcopilot.db import repo
from riskcopilot.engine.limits import check_limit
from riskcopilot.engine.runner import (
    MODEL_BY_KEY,
    RunContext,
    run_models,
    standalone_by_asset_class,
)

router = APIRouter(tags=["what-if"])


def _limits(values: dict[str, float]) -> list[s.LimitOut]:
    out = []
    for scope, lim in reference.LIMITS.items():
        c = check_limit(scope, values[scope], lim, reference.WARN_PCT)
        out.append(
            s.LimitOut(
                scope=scope,
                limit_usd=lim,
                value_usd=c.value,
                utilisation=c.utilisation,
                status=c.status,
                warn_pct=reference.WARN_PCT,
            )
        )
    return out


@router.post("/whatif", response_model=s.WhatIfResult)
def whatif(session: SessionDep, req: s.WhatIfRequest) -> s.WhatIfResult:
    settings = get_settings()
    as_of = resolve_as_of(session, req.as_of)
    unknown = (set(req.set_exposure) | set(req.change_exposure)) - set(reference.BASE_POSITIONS)
    if unknown:
        raise HTTPException(422, f"Unknown tickers: {sorted(unknown)}")
    bad_models = [k for k in req.models if k not in MODEL_BY_KEY]
    if bad_models:
        raise HTTPException(422, f"Unknown models: {bad_models}")

    returns = repo.load_returns(session)
    if returns.empty:
        raise HTTPException(404, "No returns stored yet")
    hist = returns.loc[: str(as_of)]
    before = repo.positions_on(session, as_of)
    after = dict(before)
    after.update(req.set_exposure)
    for t, dv in req.change_exposure.items():
        after[t] = after.get(t, 0.0) + dv

    ctx = RunContext(
        settings.mc_paths, settings.mc_seed, settings.stress_start, settings.stress_end
    )
    acls = reference.asset_class_of()
    models = tuple(req.models)
    b = {(r.model, r.confidence): r for r in run_models(hist, before, acls, ctx, models)}
    a = {(r.model, r.confidence): r for r in run_models(hist, after, acls, ctx, models)}
    figures = [
        s.WhatIfFigure(
            model=k[0],
            confidence=k[1],
            var_before=b[k].var,
            var_after=a[k].var,
            es_before=b[k].es,
            es_after=a[k].es,
        )
        for k in b
        if k in a
    ]
    pm, pc = settings.primary_model, settings.primary_confidence
    return s.WhatIfResult(
        as_of=as_of,
        exposures_before=before,
        exposures_after=after,
        figures=figures,
        limits_before=_limits(standalone_by_asset_class(pm, hist, before, acls, pc, ctx)),
        limits_after=_limits(standalone_by_asset_class(pm, hist, after, acls, pc, ctx)),
    )
