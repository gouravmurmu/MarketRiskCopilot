import numpy as np
import pandas as pd
import pytest

from riskcopilot.reference import INSTRUMENTS, Instrument


def synthetic_prices(
    start: str = "2018-01-01", end: str = "2021-03-31", seed: int = 7
) -> pd.DataFrame:
    """Correlated GBM prices for the sample tickers, with a volatility spike in 2020."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, end)
    n = len(INSTRUMENTS)
    base_vol = np.linspace(0.006, 0.02, n)
    corr = 0.3 * np.ones((n, n)) + 0.7 * np.eye(n)
    chol = np.linalg.cholesky(corr)
    shocks = rng.standard_normal((len(dates), n)) @ chol.T
    vol_mult = np.where((dates >= "2020-02-20") & (dates <= "2020-05-01"), 3.0, 1.0)[:, None]
    rets = shocks * base_vol * vol_mult
    prices = 100 * np.exp(np.cumsum(rets, axis=0))
    df = pd.DataFrame(prices, index=dates, columns=[i.ticker for i in INSTRUMENTS])
    df["INR=X"] = 70 * df["INR=X"] / 100  # quoted as INR per USD
    # India trades on some US holidays and vice versa: knock out a few INDA prints.
    df.loc[df.index[::97], "INDA"] = np.nan
    return df


class FakePrices:
    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df

    def prices(self, instruments: list[Instrument], start: str, end: str | None) -> pd.DataFrame:
        out = self.df.loc[start:]
        if end:
            out = out.loc[: pd.Timestamp(end) - pd.Timedelta(days=1)]
        return out[[i.ticker for i in instruments]]


@pytest.fixture(scope="session")
def prices() -> pd.DataFrame:
    return synthetic_prices()
