"""Reference data: the sample portfolio, its instruments, limits and FRED series.

The portfolio is fictional and built only from public tickers.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Instrument:
    ticker: str
    name: str
    asset_class: str
    currency: str = "USD"
    # FX quoted as foreign-per-USD (e.g. INR=X) must be inverted to get USD per unit.
    inverse_quote: bool = False
    stooq_symbol: str | None = None


INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument("SPY", "S&P 500 ETF", "Equity", stooq_symbol="spy.us"),
    Instrument("QQQ", "Nasdaq-100 ETF", "Equity", stooq_symbol="qqq.us"),
    Instrument("NVDA", "Nvidia", "Equity", stooq_symbol="nvda.us"),
    Instrument("AAPL", "Apple", "Equity", stooq_symbol="aapl.us"),
    Instrument("XLF", "US financials ETF", "Equity", stooq_symbol="xlf.us"),
    Instrument("EFA", "Developed ex-US equity ETF", "Equity", stooq_symbol="efa.us"),
    Instrument("INDA", "India equity ETF", "Equity", stooq_symbol="inda.us"),
    Instrument("TLT", "20+ year Treasury ETF", "Rates", stooq_symbol="tlt.us"),
    Instrument("IEF", "7-10 year Treasury ETF", "Rates", stooq_symbol="ief.us"),
    Instrument("LQD", "Investment-grade corporate bond ETF", "Credit", stooq_symbol="lqd.us"),
    Instrument("HYG", "High-yield bond ETF", "Credit", stooq_symbol="hyg.us"),
    Instrument("GLD", "Gold ETF", "Commodities", stooq_symbol="gld.us"),
    Instrument("USO", "Oil ETF", "Commodities", stooq_symbol="uso.us"),
    Instrument("EURUSD=X", "Long EUR cash", "FX", currency="EUR", stooq_symbol="eurusd"),
    Instrument(
        "INR=X", "Long INR cash", "FX", currency="INR", inverse_quote=True, stooq_symbol="usdinr"
    ),
)

ASSET_CLASSES = ("Equity", "Rates", "Credit", "Commodities", "FX")

# Target USD exposure per instrument. Exposures are held constant between position changes
# (daily rebalanced to target), which keeps P&L linear: dP = w . r
BASE_POSITIONS: dict[str, float] = {
    "SPY": 1_500_000,
    "QQQ": 1_000_000,
    "NVDA": 500_000,
    "AAPL": 500_000,
    "XLF": 500_000,
    "EFA": 700_000,
    "INDA": 600_000,
    "TLT": 1_200_000,
    "IEF": 800_000,
    "LQD": 700_000,
    "HYG": 500_000,
    "GLD": 500_000,
    "USO": 300_000,
    "EURUSD=X": 400_000,
    "INR=X": 300_000,
}

BASE_POSITIONS_AS_OF = date(2015, 1, 2)

# A few simulated trades so the daily VaR attribution has real position changes to explain.
SIMULATED_TRADES: tuple[tuple[date, str, float], ...] = (
    (date(2026, 9, 15), "NVDA", 750_000),
    (date(2026, 10, 1), "GLD", 650_000),
    (date(2026, 10, 20), "TLT", 900_000),
)

# 1-day 99% VaR limits in USD. Warning at 80% utilisation, breach at 100%.
LIMITS: dict[str, float] = {
    "Portfolio": 200_000,
    "Equity": 175_000,
    "Rates": 40_000,
    "Commodities": 30_000,
    "Credit": 20_000,
    "FX": 15_000,
}
WARN_PCT = 0.80

FRED_SERIES: dict[str, str] = {
    "DGS10": "10-year Treasury yield",
    "DGS2": "2-year Treasury yield",
    "T10Y2Y": "10y-2y curve slope",
    "VIXCLS": "VIX",
    "BAMLH0A0HYM2": "High-yield OAS",
    "DEXINUS": "INR per USD",
    "SOFR": "SOFR",
}


def positions_on(as_of: date) -> dict[str, float]:
    """Target exposures effective on a date (latest change on or before it)."""
    book = dict(BASE_POSITIONS)
    for trade_date, ticker, notional in sorted(SIMULATED_TRADES):
        if trade_date <= as_of:
            book[ticker] = notional
    return book


def asset_class_of() -> dict[str, str]:
    return {i.ticker: i.asset_class for i in INSTRUMENTS}
