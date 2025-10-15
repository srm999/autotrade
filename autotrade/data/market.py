"""Market data utilities for driving strategies."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from autotrade.broker.robinhood_client import RobinhoodClient


@dataclass(slots=True)
class Quote:
    ticker: str
    price: float
    as_of: datetime


class MarketDataService:
    def __init__(self, client: RobinhoodClient) -> None:
        self._client = client

    def latest_quote(self, ticker: str) -> Quote:
        price = self._client.get_last_trade_price(ticker)
        return Quote(ticker=ticker, price=price, as_of=self._client.now())

    def historical_dataframe(self, ticker: str, span: str = "day", interval: str = "5minute") -> pd.DataFrame:
        records = self._client.get_historical_quotes(ticker, span=span, interval=interval)
        if not records:
            raise ValueError(f"No historical data returned for {ticker}")
        frame = pd.DataFrame(records)
        frame["begins_at"] = pd.to_datetime(frame["begins_at"])
        numeric_cols = {col for col in frame.columns if col.endswith("_price")}
        for col in numeric_cols:
            frame[col] = frame[col].astype(float)
        return frame.set_index("begins_at").sort_index()
