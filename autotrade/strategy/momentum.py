"""Simple momentum strategy that buys breakouts to new highs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from autotrade.config import BotConfig, MomentumParams
from autotrade.data.market import MarketDataService, Quote
from autotrade.strategy.base import Signal, StrategyDiagnostics


@dataclass(slots=True)
class _TickerPosition:
    """Track position state per ticker."""
    active: bool = False
    entry_price: float | None = None
    entry_time: datetime | None = None
    highest_high: float | None = None  # Track highest price during trade

    def reset(self) -> None:
        self.active = False
        self.entry_price = None
        self.entry_time = None
        self.highest_high = None


class MomentumStrategy:
    """
    Pure momentum strategy that buys breakouts to new highs.

    Strategy Logic:
    - Calculate 20-day high and low
    - Entry: Price breaks above 20-day high by 2% (strong momentum)
    - Exit: Price drops 3% from entry (stop loss)
    - Exit: Price held for max 5 days (time stop)

    This strategy works best in trending markets.
    Simple, robust, and has 40+ years of academic research support.
    """

    def __init__(self, config: BotConfig, data_service: MarketDataService) -> None:
        self._config = config
        self._data_service = data_service
        params = config.strategy.params
        if not isinstance(params, MomentumParams):
            raise TypeError("Strategy parameters must be MomentumParams.")
        self._params = params
        self._tickers = config.strategy.tickers

        # Track positions per ticker
        self._positions: dict[str, _TickerPosition] = {
            ticker: _TickerPosition() for ticker in self._tickers
        }

        # Cache historical data
        self._history_loaded_date: dict[str, datetime.date] = {}
        self._highest_high: dict[str, float] = {}
        self._lowest_low: dict[str, float] = {}
        self._last_price: dict[str, float] = {}

        # Trade throttling: max one signal per ticker per day
        self._last_signal_date: dict[str, datetime.date] = {}

        # Flatten tracking
        self._flattened_date: datetime.date | None = None

    def should_flatten(self, *, timestamp: datetime) -> bool:
        """Close all positions before market close."""
        close_time = self._config.trading_window.market_close
        flatten_delta = timedelta(minutes=self._params.flatten_minutes_before_close)
        close_dt = datetime.combine(timestamp.date(), close_time)

        if timestamp >= close_dt - flatten_delta:
            # Reset all positions
            for position in self._positions.values():
                position.reset()
            self._flattened_date = timestamp.date()
            return True
        return False

    def on_quote(self, quote: Quote, *, timestamp: datetime) -> Signal | None:
        """Process quote and generate trading signal."""
        ticker = quote.ticker

        # Don't trade after flatten
        if self._flattened_date == timestamp.date():
            return None

        # Refresh historical data if needed
        self._maybe_refresh_history(ticker, timestamp)

        # Need high/low calculated
        if ticker not in self._highest_high or ticker not in self._lowest_low:
            return None

        # Store current price
        self._last_price[ticker] = quote.price

        # Update trailing high if in position
        if self._positions[ticker].active:
            if self._positions[ticker].highest_high is None or quote.price > self._positions[ticker].highest_high:
                self._positions[ticker].highest_high = quote.price

        # Generate signal
        return self._evaluate_signal(ticker, quote.price, timestamp)

    def diagnostics(self, *, timestamp: datetime) -> StrategyDiagnostics:
        """Return current strategy state."""
        metrics = {}
        active_positions = {}

        for ticker in self._tickers:
            metrics[ticker] = {
                "highest_high": self._highest_high.get(ticker, float("nan")),
                "lowest_low": self._lowest_low.get(ticker, float("nan")),
                "last_price": self._last_price.get(ticker, float("nan")),
                "breakout_level": self._highest_high.get(ticker, 0) * (1 + self._params.breakout_pct),
            }
            active_positions[ticker] = self._positions[ticker].active

        return StrategyDiagnostics(
            timestamp=timestamp,
            regime=None,
            target_ticker=None,
            active_positions=active_positions,
            latest_metrics=metrics,
            flattened_today=self._flattened_date == timestamp.date(),
            extras={},
        )

    # --- Internal helpers ---

    def _maybe_refresh_history(self, ticker: str, timestamp: datetime) -> None:
        """Load historical data to calculate highs and lows."""
        if self._history_loaded_date.get(ticker) == timestamp.date():
            return  # Already loaded today

        try:
            # Get daily historical data
            df = self._data_service.historical_dataframe(ticker, span="year", interval="daily")
        except ValueError:
            return

        if df.empty or "high_price" not in df.columns or "low_price" not in df.columns:
            return

        high_prices = df["high_price"].astype(float)
        low_prices = df["low_price"].astype(float)

        # Need at least lookback_days
        if len(high_prices) < self._params.lookback_days:
            return

        # Calculate highest high and lowest low
        recent_highs = high_prices.tail(self._params.lookback_days)
        recent_lows = low_prices.tail(self._params.lookback_days)

        highest = recent_highs.max()
        lowest = recent_lows.min()

        if pd.isna(highest) or pd.isna(lowest):
            return

        self._highest_high[ticker] = float(highest)
        self._lowest_low[ticker] = float(lowest)
        self._history_loaded_date[ticker] = timestamp.date()

    def _evaluate_signal(self, ticker: str, price: float, timestamp: datetime) -> Signal | None:
        """Determine if we should enter or exit position."""
        position = self._positions[ticker]

        if position.active:
            return self._maybe_exit(ticker, price, timestamp)
        else:
            return self._maybe_enter(ticker, price, timestamp)

    def _maybe_enter(self, ticker: str, price: float, timestamp: datetime) -> Signal | None:
        """Check for entry signal (breakout to new high)."""
        # Only allow one signal per ticker per day
        today = timestamp.date()
        if self._last_signal_date.get(ticker) == today:
            return None

        highest_high = self._highest_high.get(ticker)
        if highest_high is None or highest_high <= 0:
            return None

        # Entry: Price breaks above highest high by breakout_pct
        breakout_level = highest_high * (1 + self._params.breakout_pct)

        if price > breakout_level:
            self._positions[ticker].active = True
            self._positions[ticker].entry_price = price
            self._positions[ticker].entry_time = timestamp
            self._positions[ticker].highest_high = price
            self._last_signal_date[ticker] = today

            return Signal(
                ticker=ticker,
                side="buy",
                quantity=None,  # Use default position sizing
                metadata={
                    "reason": "momentum_breakout",
                    "entry_price": price,
                    "highest_high": highest_high,
                    "breakout_pct": self._params.breakout_pct,
                }
            )

        return None

    def _maybe_exit(self, ticker: str, price: float, timestamp: datetime) -> Signal | None:
        """Check for exit signal (stop loss or time stop)."""
        position = self._positions[ticker]

        if not position.active or position.entry_price is None:
            return None

        reason = None

        # Exit 1: Stop loss - price drops X% from entry
        loss_pct = (price - position.entry_price) / position.entry_price
        if loss_pct <= -abs(self._params.stop_loss_pct):
            reason = "stop_loss"

        # Exit 2: Time-based stop (held too long)
        elif position.entry_time:
            held_days = (timestamp - position.entry_time).days
            if held_days >= self._params.max_hold_days:
                reason = "time_stop"

        # Exit 3: Trailing stop (optional) - price drops 50% from peak
        # This protects profits after a strong run
        if not reason and position.highest_high and position.entry_price:
            # Calculate profit from entry to peak
            peak_profit_pct = (position.highest_high - position.entry_price) / position.entry_price

            # If we had > 10% profit, use trailing stop
            if peak_profit_pct > 0.10:
                pullback_from_peak = (price - position.highest_high) / position.highest_high
                if pullback_from_peak < -0.05:  # 5% pullback from peak
                    reason = "trailing_stop"

        if reason:
            self._positions[ticker].reset()

            return Signal(
                ticker=ticker,
                side="sell",
                quantity=None,  # Sell entire position
                metadata={
                    "reason": f"momentum_{reason}",
                    "exit_price": price,
                    "entry_price": position.entry_price,
                    "highest_high": position.highest_high,
                }
            )

        return None
