"""Local persistence for historical market data."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


class HistoryStore:
    """Simple CSV-backed cache for per-ticker historical data."""

    def __init__(self, root: str | Path = "data/history") -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def load(self, ticker: str) -> pd.DataFrame:
        path = self._path(ticker)
        if not path.exists():
            return pd.DataFrame()
        frame = pd.read_csv(path, parse_dates=["begins_at"])
        if "begins_at" not in frame.columns:
            return pd.DataFrame()
        frame = frame.set_index("begins_at").sort_index()
        return frame

    def save(self, ticker: str, frame: pd.DataFrame, *, columns: Iterable[str] | None = None) -> None:
        if frame.empty:
            return
        to_persist = frame.copy()
        if columns:
            missing = [col for col in columns if col not in to_persist.columns]
            if missing:
                raise ValueError(f"Cannot persist {ticker}; missing columns: {missing}")
            to_persist = to_persist[list(columns)]
        to_persist = to_persist.sort_index()
        output = to_persist.reset_index()
        output.to_csv(self._path(ticker), index=False)

    def upsert(self, ticker: str, frame: pd.DataFrame) -> pd.DataFrame:
        """Merge incoming rows with the existing cache and persist."""
        if frame.empty:
            return self.load(ticker)
        existing = self.load(ticker)
        combined = pd.concat([existing, frame])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined.sort_index()
        self.save(ticker, combined)
        return combined

    def _path(self, ticker: str) -> Path:
        safe = ticker.upper().replace("/", "_")
        return self._root / f"{safe}.csv"
