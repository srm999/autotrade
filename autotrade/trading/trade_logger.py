"""Lightweight CSV trade logger with running daily PnL."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class TradeRecord:
    timestamp: datetime
    ticker: str
    side: str
    quantity: int
    price: float
    notional: float
    reason: str
    metadata: dict[str, Any]
    realized_pnl: float
    cumulative_pnl: float
    position_quantity: float
    position_avg_cost: float


class TradeLogger:
    """Append-only CSV logger that keeps daily realized PnL totals."""

    def __init__(self, root: str | Path = "data/trades") -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._daily_totals: dict[date, float] = {}

    def record(self, record: TradeRecord) -> None:
        day = record.timestamp.date()
        running = self._daily_totals.get(day, 0.0) + record.realized_pnl
        self._daily_totals[day] = running
        record.cumulative_pnl = running
        path = self._root / f"{day.isoformat()}.csv"
        file_exists = path.exists()
        with path.open("a", newline="") as handle:
            writer = csv.writer(handle)
            if not file_exists:
                writer.writerow(
                    [
                        "timestamp",
                        "ticker",
                        "side",
                        "quantity",
                        "price",
                        "notional",
                        "reason",
                        "metadata",
                        "realized_pnl",
                        "cumulative_pnl",
                        "position_quantity",
                        "position_avg_cost",
                    ]
                )
            writer.writerow(
                [
                    record.timestamp.isoformat(),
                    record.ticker,
                    record.side,
                    record.quantity,
                    f"{record.price:.4f}",
                    f"{record.notional:.2f}",
                    record.reason,
                    self._format_metadata(record.metadata),
                    f"{record.realized_pnl:.2f}",
                    f"{running:.2f}",
                    f"{record.position_quantity:.4f}",
                    f"{record.position_avg_cost:.4f}",
                ]
            )

    @staticmethod
    def _format_metadata(metadata: dict[str, Any]) -> str:
        if not metadata:
            return ""
        try:
            return "; ".join(f"{key}={value}" for key, value in metadata.items())
        except Exception:
            return str(metadata)
