"""Dual moving-average regime filter with mean reversion entries for TQQQ/SQQQ."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from autotrade.config import BotConfig, DualMAMeanReversionParams
from autotrade.data.market import MarketDataService, Quote
from autotrade.strategy.base import Signal


@dataclass(slots=True)
class _PositionState:
    active: bool = False
    entry_price: float | None = None
    entry_time: datetime | None = None

    def reset(self) -> None:
        self.active = False
        self.entry_price = None
        self.entry_time = None


class DualMAMeanReversionStrategy:
    """Daily regime filter backed by a 50/250-day SMA with z-score entries."""

    def __init__(self, config: BotConfig, data_service: MarketDataService) -> None:
        self._config = config
        self._data_service = data_service
        self._params: DualMAMeanReversionParams = config.strategy.params
        self._history: dict[str, pd.DataFrame] = {}
        self._last_history_sync: datetime | None = None
        self._position: dict[str, _PositionState] = {
            ticker: _PositionState() for ticker in config.strategy.tickers
        }
        self._regime: str | None = None  # "risk_on" -> TQQQ, "risk_off" -> SQQQ
        self._flattened_date: datetime.date | None = None
        self._last_signal_date: dict[tuple[str, str], datetime.date] = {}

    def should_flatten(self, *, timestamp: datetime) -> bool:
        close_time = self._config.trading_window.market_close
        flatten_delta = timedelta(minutes=self._params.flatten_minutes_before_close)
        close_dt = datetime.combine(timestamp.date(), close_time)
        if timestamp >= close_dt - flatten_delta:
            if any(state.active for state in self._position.values()):
                for state in self._position.values():
                    state.reset()
                self._flattened_date = timestamp.date()
                return True
        return False

    def on_quote(self, quote: Quote, *, timestamp: datetime) -> Signal | None:
        if self._flattened_date == timestamp.date():
            return None
        self._maybe_refresh_history(timestamp)
        if quote.ticker not in self._history or self._history[quote.ticker].empty:
            return None

        self._update_regime()
        active_ticker = self._current_position_ticker()
        target_ticker = self._target_ticker()

        if active_ticker and active_ticker != quote.ticker:
            # Let the held ticker manage its own exits; ignore other symbols until flat.
            return None

        metrics = self._latest_metrics(quote.ticker)
        if not metrics:
            return None

        # Exit logic first (includes regime flips, z-score exits, and stops).
        exit_signal = self._maybe_exit(quote, metrics, timestamp, target_ticker)
        if exit_signal:
            return exit_signal

        # Only the regime-preferred ticker should attempt new entries.
        if quote.ticker != target_ticker:
            return None

        entry_signal = self._maybe_enter(quote, metrics, timestamp)
        if entry_signal:
            return entry_signal
        return None

    # --- Internal helpers -------------------------------------------------

    def _maybe_refresh_history(self, timestamp: datetime) -> None:
        if (
            self._last_history_sync
            and self._last_history_sync.date() == timestamp.date()
        ):
            return
        lookback = max(
            self._params.slow_window,
            self._params.fast_window,
            self._params.std_lookback,
        ) + 50
        for ticker in self._config.strategy.tickers:
            frame = self._data_service.historical_dataframe(
                ticker, span=self._span_for_lookback(lookback), interval="day"
            )
            if frame.empty:
                self._history[ticker] = pd.DataFrame()
                continue
            frame = frame.tail(lookback).copy()
            frame["close"] = frame["close_price"].astype(float)
            frame["sma_fast"] = (
                frame["close"].rolling(self._params.fast_window).mean()
            )
            frame["sma_slow"] = (
                frame["close"].rolling(self._params.slow_window).mean()
            )
            frame["rolling_std"] = frame["close"].rolling(
                self._params.std_lookback
            ).std()
            frame["z_score"] = (
                (frame["close"] - frame["sma_fast"]) / frame["rolling_std"]
            )
            # Drop rows where indicators are unavailable.
            frame = frame.dropna(subset=["sma_fast", "sma_slow", "rolling_std", "z_score"])
            self._history[ticker] = frame
        self._last_history_sync = timestamp

    def _update_regime(self) -> None:
        source = self._history.get("TQQQ")
        if source is None or source.empty:
            return
        confirm = self._params.regime_confirm_days
        if len(source) < confirm:
            return
        window = source.tail(confirm)
        fast_over_slow = (window["sma_fast"] > window["sma_slow"]).all()
        fast_under_slow = (window["sma_fast"] < window["sma_slow"]).all()
        if fast_over_slow:
            self._regime = "risk_on"
        elif fast_under_slow:
            self._regime = "risk_off"

    def _target_ticker(self) -> str | None:
        if self._regime == "risk_on":
            return "TQQQ"
        if self._regime == "risk_off":
            return "SQQQ"
        return None

    def _current_position_ticker(self) -> str | None:
        for ticker, state in self._position.items():
            if state.active:
                return ticker
        return None

    def _latest_metrics(self, ticker: str) -> dict[str, Any] | None:
        frame = self._history.get(ticker)
        if frame is None or frame.empty:
            return None
        latest = frame.iloc[-1]
        if pd.isna(latest["z_score"]):
            return None
        return {
            "close": float(latest["close"]),
            "sma_fast": float(latest["sma_fast"]),
            "sma_slow": float(latest["sma_slow"]),
            "z_score": float(latest["z_score"]),
        }

    def _maybe_exit(
        self,
        quote: Quote,
        metrics: dict[str, Any],
        timestamp: datetime,
        target_ticker: str | None,
    ) -> Signal | None:
        state = self._position[quote.ticker]
        if not state.active:
            return None
        params = self._params
        today = timestamp.date()
        if self._last_signal_date.get((quote.ticker, "sell")) == today:
            return None

        # Regime flip forces a full exit before considering new entries.
        if target_ticker != quote.ticker:
            self._clear_position(quote.ticker)
            self._last_signal_date[(quote.ticker, "sell")] = today
            return Signal(ticker=quote.ticker, side="sell", metadata={"reason": "regime_flip"})

        # Stop loss
        if state.entry_price:
            drawdown = (quote.price - state.entry_price) / state.entry_price
            if drawdown <= -params.stop_loss_pct:
                self._clear_position(quote.ticker)
                self._last_signal_date[(quote.ticker, "sell")] = today
                return Signal(
                    ticker=quote.ticker,
                    side="sell",
                    metadata={"reason": "stop", "drawdown": drawdown},
                )

        z = metrics["z_score"]
        exit_threshold = abs(params.exit_zscore)
        if quote.ticker == "TQQQ" and z >= exit_threshold:
            self._clear_position(quote.ticker)
            self._last_signal_date[(quote.ticker, "sell")] = today
            return Signal(ticker=quote.ticker, side="sell", metadata={"reason": "mean_revert"})
        if quote.ticker == "SQQQ" and z <= exit_threshold:
            self._clear_position(quote.ticker)
            self._last_signal_date[(quote.ticker, "sell")] = today
            return Signal(ticker=quote.ticker, side="sell", metadata={"reason": "mean_revert"})
        return None

    def _maybe_enter(
        self,
        quote: Quote,
        metrics: dict[str, Any],
        timestamp: datetime,
    ) -> Signal | None:
        state = self._position[quote.ticker]
        if state.active:
            return None
        params = self._params
        today = timestamp.date()
        if self._last_signal_date.get((quote.ticker, "buy")) == today:
            return None
        z = metrics["z_score"]

        if quote.ticker == "TQQQ":
            should_enter = z <= -params.entry_zscore
        else:  # SQQQ
            should_enter = z >= params.entry_zscore

        if not should_enter:
            return None

        state.active = True
        state.entry_price = quote.price
        state.entry_time = timestamp
        self._last_signal_date[(quote.ticker, "buy")] = today
        notional = self._config.strategy.max_position_size
        return Signal(
            ticker=quote.ticker,
            side="buy",
            metadata={"reason": "entry", "z_score": z, "notional": notional},
        )

    def _clear_position(self, ticker: str) -> None:
        self._position[ticker].reset()

    @staticmethod
    def _span_for_lookback(lookback: int) -> str:
        if lookback <= 365:
            return "year"
        if lookback <= 365 * 5:
            return "5year"
        return "all"
