"""SQLAlchemy models for the 14 tables in the blueprint.

Every result row hangs off a risk_run that records the inputs, method, code version and
seed, so any reported number can be reproduced. Natural keys mean a rerun of a day replaces
its results instead of duplicating them.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON}


class InstrumentRow(Base):
    __tablename__ = "instruments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    asset_class: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(8))


class Position(Base):
    __tablename__ = "positions"
    portfolio_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    quantity: Mapped[float | None] = mapped_column(Float)
    notional_usd: Mapped[float] = mapped_column(Float)


class Price(Base):
    __tablename__ = "prices"
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    close: Mapped[float | None] = mapped_column(Float)  # as quoted
    adj_close: Mapped[float] = mapped_column(Float)  # USD per unit, after any fill
    source: Mapped[str] = mapped_column(String(16))
    is_filled: Mapped[bool] = mapped_column(default=False)


class MacroSeries(Base):
    __tablename__ = "macro_series"
    series_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[float] = mapped_column(Float)


class Return(Base):
    __tablename__ = "returns"
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    simple_ret: Mapped[float] = mapped_column(Float)
    log_ret: Mapped[float] = mapped_column(Float)


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"))
    check: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(default=False)
    resolved_by: Mapped[str | None] = mapped_column(String(64))


class RiskRun(Base):
    __tablename__ = "risk_runs"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # as_of:model:conf
    as_of: Mapped[date] = mapped_column(Date, index=True)
    model: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    horizon_days: Mapped[int] = mapped_column(Integer, default=1)
    window: Mapped[int] = mapped_column(Integer)
    var_usd: Mapped[float] = mapped_column(Float)
    es_usd: Mapped[float] = mapped_column(Float)
    var_10d_usd: Mapped[float] = mapped_column(Float)
    es_10d_usd: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    code_version: Mapped[str] = mapped_column(String(64))
    seed: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RiskContribution(Base):
    __tablename__ = "risk_contributions"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("risk_runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    level: Mapped[str] = mapped_column(String(16), primary_key=True)  # position | asset_class
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    exposure_usd: Mapped[float] = mapped_column(Float)
    component_var: Mapped[float] = mapped_column(Float)
    marginal_var: Mapped[float] = mapped_column(Float)


class VarAttribution(Base):
    __tablename__ = "var_attribution"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("risk_runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    effect: Mapped[str] = mapped_column(String(32), primary_key=True)
    amount_usd: Mapped[float] = mapped_column(Float)
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class BacktestResultRow(Base):
    __tablename__ = "backtest_results"
    model: Mapped[str] = mapped_column(String(32), primary_key=True)
    confidence: Mapped[float] = mapped_column(Float, primary_key=True)
    window_end: Mapped[date] = mapped_column(Date, primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), primary_key=True)  # rolling_250 | full
    T: Mapped[int] = mapped_column(Integer)
    exceptions: Mapped[int] = mapped_column(Integer)
    expected: Mapped[float] = mapped_column(Float)
    lr_pof: Mapped[float] = mapped_column(Float)
    p_pof: Mapped[float] = mapped_column(Float)
    lr_ind: Mapped[float] = mapped_column(Float)
    p_ind: Mapped[float] = mapped_column(Float)
    lr_cc: Mapped[float] = mapped_column(Float)
    p_cc: Mapped[float] = mapped_column(Float)
    zone: Mapped[str] = mapped_column(String(8))


class Limit(Base):
    __tablename__ = "limits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(32))
    metric: Mapped[str] = mapped_column(String(32), default="var_1d_99")
    limit_usd: Mapped[float] = mapped_column(Float)
    warn_pct: Mapped[float] = mapped_column(Float, default=0.8)
    active_from: Mapped[date] = mapped_column(Date)


class LimitCheckRow(Base):
    __tablename__ = "limit_checks"
    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    limit_id: Mapped[int] = mapped_column(ForeignKey("limits.id"), primary_key=True)
    value_usd: Mapped[float] = mapped_column(Float)
    utilisation: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16))


class Commentary(Base):
    __tablename__ = "commentary"
    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    draft_md: Mapped[str | None] = mapped_column(Text)
    final_md: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    validator_report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    approved_by: Mapped[str | None] = mapped_column(String(64))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)


class AgentTrace(Base):
    __tablename__ = "agent_traces"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    as_of: Mapped[date | None] = mapped_column(Date)
    mode: Mapped[str] = mapped_column(String(16))  # daily | chat
    step: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str | None] = mapped_column(String(64))
    args_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_hash: Mapped[str | None] = mapped_column(String(64))
    tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
