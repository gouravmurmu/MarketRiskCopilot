"""Response and request models. Every risk figure is a positive USD loss number."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    key: str
    method: str
    label: str
    window: int


class Meta(BaseModel):
    latest_as_of: date | None
    first_as_of: date | None
    primary_model: str
    primary_confidence: float
    models: list[ModelInfo]


class PositionOut(BaseModel):
    ticker: str
    name: str
    asset_class: str
    notional_usd: float


class Portfolio(BaseModel):
    as_of: date
    positions_as_of: date | None
    total_usd: float
    positions: list[PositionOut]


class RiskFigure(BaseModel):
    model: str
    method: str
    label: str
    confidence: float
    var_usd: float
    es_usd: float
    var_10d_usd: float
    es_10d_usd: float
    prev_var_usd: float | None
    change_usd: float | None
    change_pct: float | None


class RiskSummary(BaseModel):
    as_of: date
    previous_as_of: date | None
    code_version: str | None
    figures: list[RiskFigure]


class HistoryPoint(BaseModel):
    date: date
    var_usd: float
    es_usd: float
    pnl_usd: float | None = Field(None, description="Hypothetical P&L on the next day")
    exception: bool | None = None


class RiskHistory(BaseModel):
    model: str
    confidence: float
    points: list[HistoryPoint]


class ContributionOut(BaseModel):
    key: str
    exposure_usd: float
    component_var: float
    marginal_var: float
    share: float


class Contributors(BaseModel):
    as_of: date
    model: str
    confidence: float
    level: str
    total_var_usd: float
    items: list[ContributionOut]


class EffectOut(BaseModel):
    effect: str
    amount_usd: float
    detail: dict[str, Any]


class Attribution(BaseModel):
    as_of: date
    model: str
    confidence: float
    previous_var_usd: float | None
    var_usd: float
    effects: list[EffectOut]


class BacktestRow(BaseModel):
    model: str
    confidence: float
    scope: str
    window_end: date
    T: int
    exceptions: int
    expected: float
    lr_pof: float
    p_pof: float
    lr_ind: float
    p_ind: float
    lr_cc: float
    p_cc: float
    zone: str


class LimitOut(BaseModel):
    scope: str
    limit_usd: float
    value_usd: float
    utilisation: float
    status: str
    warn_pct: float


class Limits(BaseModel):
    as_of: date
    model: str
    items: list[LimitOut]


class IssueOut(BaseModel):
    id: int
    date: date
    ticker: str | None
    check: str
    severity: str
    detail: str
    resolved: bool


class DataQuality(BaseModel):
    as_of: date
    blocking: bool
    issues: list[IssueOut]
    latest_price_dates: dict[str, date]


class WhatIfRequest(BaseModel):
    as_of: date | None = None
    # Either absolute target exposures or changes, in USD, keyed by ticker.
    set_exposure: dict[str, float] = Field(default_factory=dict)
    change_exposure: dict[str, float] = Field(default_factory=dict)
    models: list[str] = Field(default_factory=lambda: ["hs_500", "pn_ewma", "mc_ewma"])


class WhatIfFigure(BaseModel):
    model: str
    confidence: float
    var_before: float
    var_after: float
    es_before: float
    es_after: float


class WhatIfResult(BaseModel):
    as_of: date
    exposures_before: dict[str, float]
    exposures_after: dict[str, float]
    figures: list[WhatIfFigure]
    limits_before: list[LimitOut]
    limits_after: list[LimitOut]
