"""Strategy abstractions for the trading bot."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from autotrade.data.market import Quote


class SignalType(Enum):
    """Type of trading signal."""

    ENTRY = "entry"
    EXIT = "exit"
    HOLD = "hold"


@dataclass(slots=True)
class Signal:
    ticker: str
    side: str | None = None  # "buy", "sell", or "flat" (legacy)
    signal_type: SignalType | None = None  # New: ENTRY, EXIT, HOLD
    direction: str | None = None  # New: "long", "short"
    price: float | None = None  # New: Signal price
    confidence: float = 0.0  # New: Signal confidence (0-1)
    strength: float = 0.0  # Legacy: Signal strength
    quantity: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class StrategyDiagnostics:
    timestamp: datetime
    regime: str | None = None
    target_ticker: str | None = None
    active_positions: dict[str, bool] = field(default_factory=dict)
    latest_metrics: dict[str, dict[str, float] | None] = field(default_factory=dict)
    flattened_today: bool = False
    extras: dict[str, Any] | None = None


class Strategy(Protocol):
    """Base strategy protocol."""

    # Legacy interface (for old strategies)
    def on_quote(self, quote: Quote, *, timestamp: datetime) -> Signal | None:
        ...

    def should_flatten(self, *, timestamp: datetime) -> bool:
        ...

    def diagnostics(self, *, timestamp: datetime) -> StrategyDiagnostics:
        ...

    # New interface (for multi-strategy system)
    def is_compatible_with_regime(self, regime: Any) -> bool:
        """Check if strategy is compatible with current market regime."""
        ...

    def generate_signals(
        self, ticker: str, data: Any, regime: Any | None = None
    ) -> list[Signal]:
        """Generate trading signals for given market data."""
        ...

    def check_exit_conditions(
        self,
        ticker: str,
        entry_price: float,
        current_price: float,
        direction: str,
        days_held: int,
    ) -> tuple[bool, str | None]:
        """Check if position should be exited."""
        ...
