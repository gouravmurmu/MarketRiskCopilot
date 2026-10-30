"""Limit checks: warning at the warning threshold (default 80%), breach at 100%."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LimitCheck:
    scope: str
    value: float
    limit: float
    utilisation: float
    status: str  # ok | warning | breach


def check_limit(scope: str, value: float, limit: float, warn_pct: float = 0.8) -> LimitCheck:
    util = value / limit
    status = "breach" if util >= 1.0 else "warning" if util >= warn_pct else "ok"
    return LimitCheck(scope, value, limit, util, status)


def check_limits(
    values: dict[str, float], limits: dict[str, float], warn_pct: float = 0.8
) -> list[LimitCheck]:
    return [check_limit(s, values[s], lim, warn_pct) for s, lim in limits.items() if s in values]
