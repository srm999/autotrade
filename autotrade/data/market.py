"""Market data utilities for driving strategies."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from autotrade.broker.robinhood_client import RobinhoodClient
from autotrade.data.history_store import HistoryStore


@dataclass(slots=True)
class Quote:
    ticker: str
    price: float
    as_of: datetime


class MarketDataService:
    def __init__(self, client: RobinhoodClient, *, history_store: HistoryStore | None = None) -> None:
        self._client = client
        self._history_store = history_store or HistoryStore()

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

    def daily_history(self, ticker: str, *, lookback_days: int = 365) -> pd.DataFrame:
        stored = self._history_store.load(ticker)
        today = pd.Timestamp.utcnow().normalize()
        cutoff = today - pd.Timedelta(days=lookback_days + 5)
        if not stored.empty:
            stored = stored[stored.index >= cutoff]
        span = "5year" if lookback_days > 365 else "year"
        latest_ts = stored.index.max() if not stored.empty else None
        refresh_needed = stored.empty
        if latest_ts is not None:
            latest_ts = pd.Timestamp(latest_ts)
            if latest_ts < today - pd.Timedelta(days=1):
                refresh_needed = True
        if refresh_needed:
            fetched = self._fetch_daily_span(ticker, span=span)
            if not fetched.empty:
                stored = pd.concat([stored, fetched])
        if not stored.empty:
            stored = stored[~stored.index.duplicated(keep="last")]
            stored = stored.sort_index()
            stored = stored[stored.index >= cutoff]
            self._history_store.save(ticker, stored)
        return stored.tail(lookback_days)

    def _fetch_daily_span(self, ticker: str, *, span: str) -> pd.DataFrame:
        try:
            frame = self.historical_dataframe(ticker, span=span, interval="day")
        except ValueError:
            frame = pd.DataFrame()
        if frame.empty or "begins_at" not in frame.columns:
            return frame
        return frame[~frame.index.duplicated(keep="last")].sort_index()
