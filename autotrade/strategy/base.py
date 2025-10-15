"""Strategy abstractions for the trading bot."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from autotrade.data.market import Quote


@dataclass(slots=True)
class Signal:
    ticker: str
    side: str  # "buy", "sell", or "flat"
    strength: float = 0.0
    quantity: int | None = None
    metadata: dict[str, Any] | None = None


class Strategy(Protocol):
    def on_quote(self, quote: Quote, *, timestamp: datetime) -> Signal | None:
        ...

    def should_flatten(self, *, timestamp: datetime) -> bool:
        ...
