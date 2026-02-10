"""Circuit breaker for risk management and trading protection."""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque

from autotrade.utils.time_utils import now_utc

_LOG = logging.getLogger(__name__)


@dataclass
class TradeOutcome:
    """Record of a trade outcome for circuit breaker tracking."""
    timestamp: datetime
    realized_pnl: float
    ticker: str


class CircuitBreaker:
    """Monitors trading activity and enforces risk limits.

    Circuit breakers help prevent catastrophic losses by:
    - Halting trading after exceeding daily loss limits
    - Stopping after too many consecutive losses
    - Limiting trade frequency to prevent overtrading
    """

    def __init__(
        self,
        *,
        max_daily_loss: float,
        max_consecutive_losses: int,
        max_trades_per_hour: int,
        enabled: bool = True,
    ) -> None:
        """Initialize circuit breaker with risk parameters.

        Args:
            max_daily_loss: Maximum allowed daily loss in dollars
            max_consecutive_losses: Stop after this many consecutive losing trades
            max_trades_per_hour: Maximum number of trades allowed per hour
            enabled: Whether circuit breaker is active
        """
        self._max_daily_loss = max_daily_loss
        self._max_consecutive_losses = max_consecutive_losses
        self._max_trades_per_hour = max_trades_per_hour
        self._enabled = enabled

        self._daily_pnl = 0.0
        self._consecutive_losses = 0
        self._trade_history: Deque[TradeOutcome] = deque(maxlen=1000)
        self._recent_trades: Deque[datetime] = deque(maxlen=100)
        self._tripped = False
        self._trip_reason: str | None = None
        self._session_start = now_utc()

        _LOG.info(
            "Circuit breaker initialized: max_daily_loss=%.2f, "
            "max_consecutive_losses=%d, max_trades_per_hour=%d, enabled=%s",
            max_daily_loss,
            max_consecutive_losses,
            max_trades_per_hour,
            enabled,
        )

    def record_trade(self, ticker: str, realized_pnl: float) -> None:
        """Record a trade outcome for tracking.

        Args:
            ticker: The ticker symbol traded
            realized_pnl: Realized profit/loss from the trade
        """
        if not self._enabled:
            return

        timestamp = now_utc()
        outcome = TradeOutcome(timestamp=timestamp, realized_pnl=realized_pnl, ticker=ticker)
        self._trade_history.append(outcome)
        self._recent_trades.append(timestamp)

        # Update daily PnL
        self._daily_pnl += realized_pnl

        # Track consecutive losses
        if realized_pnl < 0:
            self._consecutive_losses += 1
            _LOG.info(
                "Trade loss recorded: %s realized_pnl=%.2f (consecutive_losses=%d, daily_pnl=%.2f)",
                ticker,
                realized_pnl,
                self._consecutive_losses,
                self._daily_pnl,
            )
        else:
            # Reset consecutive losses on any winning trade
            if self._consecutive_losses > 0:
                _LOG.info(
                    "Consecutive loss streak broken: %s realized_pnl=%.2f",
                    ticker,
                    realized_pnl,
                )
            self._consecutive_losses = 0

        # Check if circuit breaker should trip
        self._check_limits()

    def is_tripped(self) -> bool:
        """Check if circuit breaker has been tripped.

        Returns:
            True if trading should be halted
        """
        return self._tripped

    def trip_reason(self) -> str | None:
        """Get the reason the circuit breaker tripped.

        Returns:
            String describing why circuit breaker tripped, or None if not tripped
        """
        return self._trip_reason

    def can_trade(self) -> bool:
        """Check if trading is allowed.

        Returns:
            True if trading is allowed, False if circuit breaker prevents it
        """
        if not self._enabled:
            return True

        if self._tripped:
            return False

        # Check trade frequency limit
        if self._exceeds_trade_frequency():
            _LOG.warning(
                "Trade frequency limit exceeded: %d trades in last hour (max=%d)",
                self._count_recent_trades(),
                self._max_trades_per_hour,
            )
            self._trip("trade_frequency_limit")
            return False

        return True

    def reset_daily(self) -> None:
        """Reset daily tracking counters.

        Call this at the start of each trading day.
        """
        _LOG.info(
            "Resetting circuit breaker for new trading day "
            "(previous daily_pnl=%.2f, consecutive_losses=%d)",
            self._daily_pnl,
            self._consecutive_losses,
        )
        self._daily_pnl = 0.0
        self._consecutive_losses = 0
        self._tripped = False
        self._trip_reason = None
        self._session_start = now_utc()
        # Keep trade history for analysis but clear recent trades
        self._recent_trades.clear()

    def get_status(self) -> dict[str, any]:
        """Get current circuit breaker status.

        Returns:
            Dict with circuit breaker state information
        """
        return {
            "enabled": self._enabled,
            "tripped": self._tripped,
            "trip_reason": self._trip_reason,
            "daily_pnl": self._daily_pnl,
            "consecutive_losses": self._consecutive_losses,
            "trades_last_hour": self._count_recent_trades(),
            "max_daily_loss": self._max_daily_loss,
            "max_consecutive_losses": self._max_consecutive_losses,
            "max_trades_per_hour": self._max_trades_per_hour,
            "session_duration_hours": (now_utc() - self._session_start).total_seconds() / 3600,
        }

    def _check_limits(self) -> None:
        """Check if any circuit breaker limits have been exceeded."""
        # Check daily loss limit
        if self._daily_pnl <= -abs(self._max_daily_loss):
            _LOG.error(
                "CIRCUIT BREAKER TRIPPED: Daily loss limit exceeded (daily_pnl=%.2f, limit=%.2f)",
                self._daily_pnl,
                self._max_daily_loss,
            )
            self._trip("daily_loss_limit")
            return

        # Check consecutive losses
        if self._consecutive_losses >= self._max_consecutive_losses:
            _LOG.error(
                "CIRCUIT BREAKER TRIPPED: Too many consecutive losses (count=%d, limit=%d)",
                self._consecutive_losses,
                self._max_consecutive_losses,
            )
            self._trip("consecutive_losses")
            return

    def _exceeds_trade_frequency(self) -> bool:
        """Check if trade frequency exceeds hourly limit.

        Returns:
            True if too many trades in the last hour
        """
        return self._count_recent_trades() >= self._max_trades_per_hour

    def _count_recent_trades(self) -> int:
        """Count trades in the last hour.

        Returns:
            Number of trades in the last 60 minutes
        """
        now = now_utc()
        one_hour_ago = now - timedelta(hours=1)
        return sum(1 for trade_time in self._recent_trades if trade_time >= one_hour_ago)

    def _trip(self, reason: str) -> None:
        """Trip the circuit breaker with a given reason.

        Args:
            reason: String describing why circuit breaker tripped
        """
        self._tripped = True
        self._trip_reason = reason
        _LOG.critical("CIRCUIT BREAKER ACTIVATED: %s - Trading halted!", reason)
