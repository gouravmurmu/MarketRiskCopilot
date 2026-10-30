"""Market and macro data clients: yfinance (primary), Stooq (fallback) and FRED.

yfinance is an unofficial scraper, so every call retries with backoff and the pipeline
caches all history in the database and only downloads the latest days.
"""

import io
import logging
import time
from collections.abc import Callable
from functools import partial
from typing import Protocol

import pandas as pd
import requests

from riskcopilot.reference import Instrument

log = logging.getLogger(__name__)


class PriceSource(Protocol):
    def prices(self, instruments: list[Instrument], start: str, end: str | None) -> pd.DataFrame:
        """Adjusted closes as quoted (not yet USD-converted). Rows = dates, cols = tickers."""
        ...


class MacroSource(Protocol):
    def series(self, series_ids: list[str], start: str) -> pd.DataFrame: ...


def with_retry[T](fn: Callable[[], T], attempts: int = 4, base_delay: float = 2.0) -> T:
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - data vendors fail in many ways
            if i == attempts - 1:
                raise
            delay = base_delay * 2**i
            log.warning("attempt %d failed (%s); retrying in %.0fs", i + 1, exc, delay)
            time.sleep(delay)
    raise AssertionError("unreachable")


def _stooq_close(symbol: str, start: str, end: str | None) -> pd.Series:
    params = {"s": symbol, "i": "d", "d1": start.replace("-", "")}
    if end:
        params["d2"] = end.replace("-", "")
    resp = requests.get("https://stooq.com/q/d/l/", params=params, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), parse_dates=["Date"], index_col="Date")
    return df["Close"]


class YahooWithStooqFallback:
    def prices(self, instruments: list[Instrument], start: str, end: str | None) -> pd.DataFrame:
        import yfinance as yf

        tickers = [i.ticker for i in instruments]
        raw = with_retry(
            lambda: yf.download(
                tickers, start=start, end=end, auto_adjust=True, progress=False, threads=False
            )
        )
        close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        close = close.reindex(columns=tickers)
        for inst in instruments:
            col = close[inst.ticker]
            if col.notna().sum() == 0 and inst.stooq_symbol:
                log.warning("yfinance returned nothing for %s; trying Stooq", inst.ticker)
                try:
                    s = with_retry(partial(_stooq_close, inst.stooq_symbol, start, end))
                    close = close.reindex(close.index.union(s.index))
                    close[inst.ticker] = s
                except Exception as exc:  # noqa: BLE001
                    log.error("Stooq fallback failed for %s: %s", inst.ticker, exc)
        close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
        return close.sort_index()


class Fred:
    """FRED via the official API when a key is set, else the public CSV endpoint."""

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    def _one(self, sid: str, start: str) -> pd.Series:
        if self.api_key:
            resp = requests.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": sid,
                    "api_key": self.api_key,
                    "file_type": "json",
                    "observation_start": start,
                },
                timeout=30,
            )
            resp.raise_for_status()
            obs = resp.json()["observations"]
            s = pd.Series(
                {pd.Timestamp(o["date"]): o["value"] for o in obs}, name=sid, dtype="object"
            )
        else:
            resp = requests.get(
                "https://fred.stlouisfed.org/graph/fredgraph.csv",
                params={"id": sid, "cosd": start},
                timeout=30,
            )
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text), index_col=0, parse_dates=True)
            s = df.iloc[:, 0].rename(sid)
        return pd.to_numeric(s.replace(".", None), errors="coerce").dropna()

    def series(self, series_ids: list[str], start: str) -> pd.DataFrame:
        cols = {}
        for sid in series_ids:
            try:
                cols[sid] = with_retry(partial(self._one, sid, start))
            except Exception as exc:  # noqa: BLE001 - macro data is context, never blocking
                log.error("FRED %s failed: %s", sid, exc)
        return pd.DataFrame(cols).sort_index()
