"""Bollinger Band Breakout strategy for leveraged ETF momentum trading."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from autotrade.config import BotConfig, BollingerBreakoutParams
from autotrade.data.market import MarketDataService, Quote
from autotrade.strategy.base import Signal, StrategyDiagnostics


@dataclass(slots=True)
class _TickerPosition:
    """Track position state per ticker."""
    active: bool = False
    entry_price: float | None = None
    entry_time: datetime | None = None

    def reset(self) -> None:
        self.active = False
        self.entry_price = None
        self.entry_time = None


class BollingerBreakoutStrategy:
    """
    Momentum strategy that buys when price breaks above upper Bollinger Band.

    Strategy Logic:
    - Calculate 20-period SMA and standard deviation
    - Upper Band = SMA + (2 * StdDev)
    - Lower Band = SMA - (2 * StdDev)
    - Middle Band = SMA

    Entry: Price breaks above upper band (strong momentum)
    Exit: Price crosses below SMA (momentum exhausted)
    Stop Loss: Price drops below lower band (reversal)

    Works well on leveraged ETFs because they tend to gap and run.
    """

    def __init__(self, config: BotConfig, data_service: MarketDataService) -> None:
        self._config = config
        self._data_service = data_service
        params = config.strategy.params
        if not isinstance(params, BollingerBreakoutParams):
            raise TypeError("Strategy parameters must be BollingerBreakoutParams.")
        self._params = params
        self._tickers = config.strategy.tickers

        # Track positions per ticker
        self._positions: dict[str, _TickerPosition] = {
            ticker: _TickerPosition() for ticker in self._tickers
        }

        # Cache historical data per ticker
        self._history_loaded_date: dict[str, datetime.date] = {}
        self._sma: dict[str, float] = {}
        self._upper_band: dict[str, float] = {}
        self._lower_band: dict[str, float] = {}
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

        # Need bands calculated
        if ticker not in self._sma or ticker not in self._upper_band:
            return None

        # Store current price
        self._last_price[ticker] = quote.price

        # Generate signal
        return self._evaluate_signal(ticker, quote.price, timestamp)

    def diagnostics(self, *, timestamp: datetime) -> StrategyDiagnostics:
        """Return current strategy state."""
        metrics = {}
        active_positions = {}

        for ticker in self._tickers:
            metrics[ticker] = {
                "sma": self._sma.get(ticker, float("nan")),
                "upper_band": self._upper_band.get(ticker, float("nan")),
                "lower_band": self._lower_band.get(ticker, float("nan")),
                "last_price": self._last_price.get(ticker, float("nan")),
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
        """Load historical data to calculate Bollinger Bands."""
        if self._history_loaded_date.get(ticker) == timestamp.date():
            return  # Already loaded today

        try:
            # Get daily historical data for longer lookback
            df = self._data_service.historical_dataframe(ticker, span="year", interval="daily")
        except ValueError:
            return

        if df.empty or "close_price" not in df.columns:
            return

        prices = df["close_price"].astype(float)

        # Need at least lookback_period prices
        if len(prices) < self._params.lookback_period:
            return

        # Calculate Bollinger Bands using last N periods
        recent_prices = prices.tail(self._params.lookback_period)
        sma = recent_prices.mean()
        std = recent_prices.std()

        if pd.isna(sma) or pd.isna(std) or std == 0:
            return

        # Bollinger Bands
        self._sma[ticker] = float(sma)
        self._upper_band[ticker] = float(sma + (self._params.std_multiplier * std))
        self._lower_band[ticker] = float(sma - (self._params.std_multiplier * std))
        self._history_loaded_date[ticker] = timestamp.date()

    def _evaluate_signal(self, ticker: str, price: float, timestamp: datetime) -> Signal | None:
        """Determine if we should enter or exit position."""
        position = self._positions[ticker]

        if position.active:
            return self._maybe_exit(ticker, price, timestamp)
        else:
            return self._maybe_enter(ticker, price, timestamp)

    def _maybe_enter(self, ticker: str, price: float, timestamp: datetime) -> Signal | None:
        """Check for entry signal (breakout above upper band)."""
        # Only allow one signal per ticker per day (prevent overtrading)
        today = timestamp.date()
        if self._last_signal_date.get(ticker) == today:
            return None

        upper_band = self._upper_band.get(ticker)
        if upper_band is None:
            return None

        # Entry: Price breaks above upper Bollinger Band
        if price > upper_band:
            self._positions[ticker].active = True
            self._positions[ticker].entry_price = price
            self._positions[ticker].entry_time = timestamp
            self._last_signal_date[ticker] = today

            return Signal(
                ticker=ticker,
                side="buy",
                quantity=None,  # Use default position sizing
                metadata={
                    "reason": "bollinger_breakout",
                    "entry_price": price,
                    "upper_band": upper_band,
                    "sma": self._sma.get(ticker),
                }
            )

        return None

    def _maybe_exit(self, ticker: str, price: float, timestamp: datetime) -> Signal | None:
        """Check for exit signal (price crosses below SMA or stop loss)."""
        position = self._positions[ticker]

        if not position.active or position.entry_price is None:
            return None

        sma = self._sma.get(ticker)
        lower_band = self._lower_band.get(ticker)
        reason = None

        # Exit 1: Price crosses below SMA (momentum exhausted)
        if sma and price < sma:
            reason = "sma_exit"

        # Exit 2: Stop loss - price drops below lower band
        elif lower_band and price < lower_band:
            reason = "stop_loss"

        # Exit 3: Time-based stop (held too long)
        elif position.entry_time:
            held_minutes = (timestamp - position.entry_time).total_seconds() / 60
            if held_minutes >= self._params.max_hold_minutes:
                reason = "time_stop"

        if reason:
            self._positions[ticker].reset()

            return Signal(
                ticker=ticker,
                side="sell",
                quantity=None,  # Sell entire position
                metadata={
                    "reason": f"bollinger_{reason}",
                    "exit_price": price,
                    "entry_price": position.entry_price,
                }
            )

        return None
