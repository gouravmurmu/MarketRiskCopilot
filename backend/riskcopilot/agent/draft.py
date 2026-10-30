"""The structured daily commentary the model returns, and its markdown rendering.

The layout is rendered in code, never by the model, so every day reads the same way.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from riskcopilot.agent.tools import TOOL_BY_NAME


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VarLine(_Strict):
    metric: str = Field(description="e.g. 'HS 500d VaR 99% 1d'")
    value_usd: float = Field(description="Whole US dollars, copied from get_risk_summary")
    change_pct: float | None = Field(
        description="Day-over-day change in percent (5.2 means +5.2%), from change_pct x 100"
    )


class Driver(_Strict):
    driver: Literal["position", "volatility", "correlation", "window_roll", "market_data"]
    amount_usd: float = Field(description="Whole US dollars, copied from get_var_attribution")
    explanation: str


class LimitLine(_Strict):
    scope: str
    utilisation_pct: float = Field(description="Percent, utilisation x 100, one decimal")
    status: Literal["ok", "warning", "breach"]


class Draft(_Strict):
    headline: str = Field(description="One sentence: what happened to VaR and why")
    var_summary: list[VarLine]
    drivers: list[Driver]
    limits: list[LimitLine]
    backtesting: str
    market_context: str
    data_caveats: list[str]
    sources: list[str] = Field(description="Names of the tools whose outputs were used")


def output_schema() -> dict[str, Any]:
    """JSON schema for structured outputs: every object closed, no titles."""

    def clean(node: Any) -> Any:
        if isinstance(node, dict):
            node = {k: clean(v) for k, v in node.items() if k not in ("title", "default")}
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            return node
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node

    return clean(Draft.model_json_schema())  # type: ignore[no-any-return,unused-ignore]


def _k(usd: float) -> str:
    sign = "-" if usd < 0 else ""
    return f"{sign}${abs(usd) / 1000:,.1f}k"


def _signed_k(usd: float) -> str:
    return ("+" if usd >= 0 else "-") + _k(abs(usd))


def render_markdown(d: Draft, as_of: str) -> str:
    lines = [f"## Daily risk commentary, {as_of}", "", f"**{d.headline}**", ""]
    lines += ["### VaR summary", "", "| Metric | Value | Change |", "|---|---:|---:|"]
    for v in d.var_summary:
        chg = "n/a" if v.change_pct is None else f"{v.change_pct:+.1f}%"
        lines.append(f"| {v.metric} | {_k(v.value_usd)} | {chg} |")
    lines += ["", "### What drove the change", ""]
    for dr in d.drivers:
        label = dr.driver.replace("_", " ").capitalize()
        lines.append(f"- **{label}** ({_signed_k(dr.amount_usd)}): {dr.explanation}")
    lines += ["", "### Limits", "", "| Scope | Utilisation | Status |", "|---|---:|---|"]
    for lim in d.limits:
        lines.append(f"| {lim.scope} | {lim.utilisation_pct:.1f}% | {lim.status} |")
    lines += ["", "### Backtesting", "", d.backtesting, "", "### Market context", ""]
    lines += [d.market_context, ""]
    if d.data_caveats:
        lines += ["### Data caveats", ""] + [f"- {c}" for c in d.data_caveats] + [""]
    sources = [s for s in d.sources if s in TOOL_BY_NAME]
    lines.append(f"_Sources: {', '.join(sources) or 'none'}_")
    return "\n".join(lines) + "\n"
