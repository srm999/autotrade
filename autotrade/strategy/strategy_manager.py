"""Multi-strategy manager for dynamic strategy selection.

Manages multiple strategies and activates them based on market conditions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from autotrade.analysis.market_regime import MarketRegime
from autotrade.data.market import MarketData
from autotrade.strategy.base import Signal, Strategy

_LOG = logging.getLogger(__name__)


@dataclass
class StrategyAllocation:
    """Strategy allocation and status."""

    strategy: Strategy
    is_active: bool
    last_signal_time: datetime | None = None
    signals_today: int = 0
    trades_today: int = 0


class StrategyManager:
    """
    Manages multiple trading strategies.

    Responsibilities:
    - Register strategies
    - Activate/deactivate based on market regime
    - Aggregate signals from all active strategies
    - Track per-strategy performance
    """

    def __init__(self):
        """Initialize strategy manager."""
        self._strategies: dict[str, StrategyAllocation] = {}
        self._current_regime: MarketRegime | None = None

    def register_strategy(self, strategy: Strategy, auto_activate: bool = True) -> None:
        """
        Register a new strategy.

        Args:
            strategy: Strategy to register
            auto_activate: Whether to activate immediately
        """
        if strategy.name in self._strategies:
            _LOG.warning("Strategy '%s' already registered", strategy.name)
            return

        allocation = StrategyAllocation(
            strategy=strategy,
            is_active=auto_activate,
        )

        self._strategies[strategy.name] = allocation

        _LOG.info(
            "Registered strategy '%s' (active=%s)",
            strategy.name,
            auto_activate,
        )

    def update_regime(self, regime: MarketRegime) -> None:
        """
        Update market regime and activate compatible strategies.

        Args:
            regime: Current market regime
        """
        self._current_regime = regime

        _LOG.info("Updating strategies for regime: %s", regime)

        for name, allocation in self._strategies.items():
            strategy = allocation.strategy

            # Check compatibility
            is_compatible = strategy.is_compatible_with_regime(regime)

            # Update activation status
            was_active = allocation.is_active
            allocation.is_active = is_compatible

            if was_active != is_compatible:
                status = "ACTIVATED" if is_compatible else "DEACTIVATED"
                _LOG.info(
                    "Strategy '%s': %s (regime: %s)",
                    name,
                    status,
                    regime,
                )

    def generate_signals(
        self,
        ticker: str,
        data: MarketData,
    ) -> list[Signal]:
        """
        Generate signals from all active strategies.

        Args:
            ticker: Stock ticker
            data: Market data

        Returns:
            List of signals from all active strategies
        """
        all_signals = []

        for name, allocation in self._strategies.items():
            if not allocation.is_active:
                continue

            try:
                signals = allocation.strategy.generate_signals(
                    ticker=ticker,
                    data=data,
                    regime=self._current_regime,
                )

                if signals:
                    allocation.signals_today += len(signals)
                    allocation.last_signal_time = datetime.now()
                    all_signals.extend(signals)

                    _LOG.info(
                        "%s: Generated %d signals from strategy '%s'",
                        ticker,
                        len(signals),
                        name,
                    )

            except Exception as e:
                _LOG.error(
                    "Error generating signals from strategy '%s' for %s: %s",
                    name,
                    ticker,
                    e,
                )
                continue

        return all_signals

    def check_exit_conditions(
        self,
        ticker: str,
        strategy_name: str,
        entry_price: float,
        current_price: float,
        direction: str,
        days_held: int,
    ) -> tuple[bool, str | None]:
        """
        Check exit conditions for a specific strategy.

        Args:
            ticker: Stock ticker
            strategy_name: Name of strategy that opened position
            entry_price: Entry price
            current_price: Current price
            direction: Position direction (long/short)
            days_held: Days position has been held

        Returns:
            Tuple of (should_exit, exit_reason)
        """
        allocation = self._strategies.get(strategy_name)
        if not allocation:
            _LOG.warning("Unknown strategy '%s' for exit check", strategy_name)
            return False, None

        try:
            return allocation.strategy.check_exit_conditions(
                ticker=ticker,
                entry_price=entry_price,
                current_price=current_price,
                direction=direction,
                days_held=days_held,
            )
        except Exception as e:
            _LOG.error(
                "Error checking exit conditions for %s (strategy=%s): %s",
                ticker,
                strategy_name,
                e,
            )
            return False, None

    def get_active_strategies(self) -> list[str]:
        """Get list of active strategy names."""
        return [
            name
            for name, allocation in self._strategies.items()
            if allocation.is_active
        ]

    def get_strategy_status(self) -> dict[str, dict]:
        """Get status of all strategies."""
        status = {}

        for name, allocation in self._strategies.items():
            status[name] = {
                "active": allocation.is_active,
                "signals_today": allocation.signals_today,
                "trades_today": allocation.trades_today,
                "last_signal": (
                    allocation.last_signal_time.isoformat()
                    if allocation.last_signal_time
                    else None
                ),
            }

        return status

    def reset_daily_counters(self) -> None:
        """Reset daily counters for all strategies."""
        for allocation in self._strategies.values():
            allocation.signals_today = 0
            allocation.trades_today = 0

        _LOG.info("Reset daily counters for all strategies")

    @property
    def current_regime(self) -> MarketRegime | None:
        """Get current market regime."""
        return self._current_regime
