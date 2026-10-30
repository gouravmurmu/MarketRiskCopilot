"""Numeric validator for the daily commentary.

Every number in the draft must match a number in the tool outputs, allowing for how it was
written ($172.4k, 18.2%, 1.2m). Every limit in warning or breach must be reported with the
rule engine's status, and no ticker outside the portfolio may appear.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from riskcopilot import reference
from riskcopilot.agent.draft import Draft
from riskcopilot.agent.tools import TOOL_BY_NAME

# Upper-case words that are not tickers.
ACRONYMS = {
    "VAR", "ES", "HS", "FHS", "EWMA", "GARCH", "MC", "SVAR", "USD", "INR", "EUR", "JPY", "GBP",
    "FX", "VIX", "HY", "IG", "OAS", "SOFR", "UST", "US", "EM", "DM", "CPI", "FOMC", "FED",
    "GDP", "ETF", "ETFS", "PNL", "YTD", "MTD", "QTD", "DOD", "BP", "BPS", "NA", "N/A", "AI",
    "LR", "POF", "CC", "OK", "MLE", "API", "FRED", "NDX", "SPX", "TIPS", "MBS", "UK", "EU",
}  # fmt: skip

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUM = re.compile(
    r"(?<![\w.])([+-]|−)?\$?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s?(k|K|m|M|mn|bn|%|pp|bp|bps)?(?![\w])"
)
_UPPER = re.compile(r"\b[A-Z][A-Z0-9]{1,5}(?:=X)?\b")


@dataclass
class Report:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    checked: int = 0

    def fail(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)


def _pool(outputs: Any) -> list[float]:
    """Every number in the tool outputs, plus its absolute value."""
    out: list[float] = []

    def walk(x: Any) -> None:
        if isinstance(x, bool):
            return
        if isinstance(x, int | float):
            out.append(float(x))
            out.append(abs(float(x)))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(outputs)
    return out


def _matches(value: float, pool: list[float], tol: float) -> bool:
    return any(abs(value - p) <= tol for p in pool)


def _match_text_number(
    raw_sign: str | None, digits: str, frac: str | None, unit: str | None, pool: list[float]
) -> bool:
    value = float(digits.replace(",", "") + (frac or ""))
    decimals = len(frac) - 1 if frac else 0
    half = 0.5 * 10**-decimals + 1e-9
    unit = (unit or "").lower()
    if unit == "k":
        return _matches(value * 1e3, pool, half * 1e3 + 1)
    if unit in ("m", "mn"):
        return _matches(value * 1e6, pool, half * 1e6 + 1)
    if unit == "bn":
        return _matches(value * 1e9, pool, half * 1e9 + 1)
    if unit in ("%", "pp"):
        # Percent of a fraction (0.182 -> 18.2%) or a value already in percent (yields).
        return _matches(value / 100, pool, half / 100) or _matches(value, pool, half)
    if unit in ("bp", "bps"):
        return _matches(value / 100, pool, half / 100) or _matches(value / 1e4, pool, half / 1e4)
    # Plain number: dollars, counts, or levels such as VIX.
    return _matches(value, pool, max(half, 0.5))


def _text_fields(d: Draft) -> list[tuple[str, str]]:
    out = [("headline", d.headline), ("backtesting", d.backtesting)]
    out += [("market_context", d.market_context)]
    out += [(f"drivers[{i}].explanation", x.explanation) for i, x in enumerate(d.drivers)]
    out += [(f"var_summary[{i}].metric", x.metric) for i, x in enumerate(d.var_summary)]
    out += [(f"data_caveats[{i}]", c) for i, c in enumerate(d.data_caveats)]
    return out


# Numbers that are part of names, not figures: "99%" in a metric name, "10-year", "1d".
_NAME_NUMBERS = re.compile(
    r"\b\d+(?:\.\d+)?%?\s?(?:-?(?:day|d|year|yr|y|month|m)\b)|\b(?:VaR|ES)\s?\d+(?:\.\d+)?%"
    r"|\b(?:HS|hs)[ _]?\d+d?\b|\b\d{2,3}d\b|\b2s10s\b|\b10y-2y\b|\bNasdaq-100\b|\bS&P ?500\b"
)


def validate(draft: Draft, outputs: dict[str, Any], tickers: set[str] | None = None) -> Report:
    rep = Report()
    pool = _pool(outputs)
    # Model windows and confidence levels may be named, e.g. "HS 500-day VaR at 99%".
    pool += [250, 500, 99, 97.5, 0.99, 0.975, 1, 10, 20, 60]

    # 1. Structured numbers.
    for i, v in enumerate(draft.var_summary):
        rep.checked += 1
        if not _matches(v.value_usd, pool, max(1.0, 0.0005 * abs(v.value_usd))):
            rep.fail(f"var_summary[{i}].value_usd {v.value_usd:,.0f} is not in any tool output")
        if v.change_pct is not None:
            rep.checked += 1
            if not _matches(v.change_pct / 100, pool, 0.0006):
                rep.fail(f"var_summary[{i}].change_pct {v.change_pct} is not in any tool output")
    for i, dr in enumerate(draft.drivers):
        rep.checked += 1
        if not _matches(dr.amount_usd, pool, max(1.0, 0.0005 * abs(dr.amount_usd))):
            rep.fail(f"drivers[{i}].amount_usd {dr.amount_usd:,.0f} is not in any tool output")
    for i, lim in enumerate(draft.limits):
        rep.checked += 1
        if not _matches(lim.utilisation_pct / 100, pool, 0.0006):
            rep.fail(f"limits[{i}].utilisation_pct {lim.utilisation_pct} is not in any tool output")

    # 2. Numbers inside the prose.
    for name, text in _text_fields(draft):
        clean = _NAME_NUMBERS.sub(" ", _DATE.sub(" ", text))
        for mt in _NUM.finditer(clean):
            sign, digits, frac, unit = mt.groups()
            if not unit and not frac and float(digits.replace(",", "")) <= 10:
                continue  # small counts such as "two of five" written as digits
            rep.checked += 1
            if not _match_text_number(sign, digits, frac, unit, pool):
                rep.fail(f"{name}: '{mt.group(0).strip()}' does not match any tool output")

    # 3. Every warning or breach must be reported with the engine's status.
    limits = next((v for k, v in outputs.items() if k.startswith("get_limit_status")), None) or {}
    reported = {lim.scope.lower(): lim.status for lim in draft.limits}
    for item in limits.get("items", []):
        if item["status"] in ("warning", "breach"):
            got = reported.get(item["scope"].lower())
            if got is None:
                rep.fail(f"Limit {item['scope']} is in {item['status']} but is not reported")
            elif got != item["status"]:
                rep.fail(f"Limit {item['scope']} is {item['status']}, the draft says {got}")
    for lim in draft.limits:
        engine = next(
            (x for x in limits.get("items", []) if x["scope"].lower() == lim.scope.lower()), None
        )
        if engine is None:
            rep.fail(f"Limit scope {lim.scope!r} does not exist")
        elif engine["status"] != lim.status:
            rep.fail(f"Limit {lim.scope} is {engine['status']}, the draft says {lim.status}")

    # 4. No tickers outside the portfolio.
    allowed = (tickers or set(reference.BASE_POSITIONS)) | ACRONYMS | set(reference.FRED_SERIES)
    allowed |= {lim.lower() for lim in reference.LIMITS} | {x.upper() for x in reference.LIMITS}
    for name, text in _text_fields(draft):
        for tok in _UPPER.findall(text):
            if tok.upper() not in {a.upper() for a in allowed}:
                rep.fail(f"{name}: '{tok}' is not a portfolio ticker")

    # 5. Sources must be real tools.
    for src in draft.sources:
        if src not in TOOL_BY_NAME:
            rep.fail(f"sources: unknown tool {src!r}")
    return rep
