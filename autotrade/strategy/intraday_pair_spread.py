"""Intraday mean-reversion strategy that trades the spread between two symbols."""
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd

from autotrade.config import BotConfig, IntradayPairSpreadParams
from autotrade.data.market import MarketDataService, Quote
from autotrade.strategy.base import Signal, StrategyDiagnostics


@dataclass(slots=True)
class _PairPosition:
    active: bool = False
    direction: str | None = None  # "long_a" or "long_b"
    entry_time: datetime | None = None
    entry_zscore: float | None = None

    def reset(self) -> None:
        self.active = False
        self.direction = None
        self.entry_time = None
        self.entry_zscore = None


class IntradayPairSpreadStrategy:
    """Pairs trading strategy that enters when the intraday spread deviates by a z-score."""

    def __init__(self, config: BotConfig, data_service: MarketDataService) -> None:
        if len(config.strategy.tickers) != 2:
            raise ValueError("IntradayPairSpreadStrategy requires exactly two tickers.")
        self._config = config
        self._data_service = data_service
        params = config.strategy.params
        if not isinstance(params, IntradayPairSpreadParams):
            raise TypeError("Strategy parameters must be IntradayPairSpreadParams.")
        self._params = params
        self._pair = tuple(config.strategy.tickers)
        self._history_loaded_date: datetime.date | None = None
        self._spread_window: deque[float] = deque(maxlen=self._params.lookback_bars)
        self._position = _PairPosition()
        self._latest_quotes: Dict[str, Quote] = {}
        self._pending_signals: Dict[str, List[Signal]] = defaultdict(list)
        self._cooldown_until: datetime | None = None
        self._last_spread_timestamp: datetime | None = None
        self._latest_zscore: float | None = None
        self._latest_spread: float | None = None
        self._latest_mean: float | None = None
        self._latest_std: float | None = None
        self._flattened_date: datetime.date | None = None

    def should_flatten(self, *, timestamp: datetime) -> bool:
        close_time = self._config.trading_window.market_close
        flatten_delta = timedelta(minutes=self._params.flatten_minutes_before_close)
        close_dt = datetime.combine(timestamp.date(), close_time)
        if timestamp >= close_dt - flatten_delta:
            if self._position.active:
                self._position.reset()
            self._pending_signals.clear()
            self._flattened_date = timestamp.date()
            return True
        return False

    def on_quote(self, quote: Quote, *, timestamp: datetime) -> Signal | None:
        if self._flattened_date == timestamp.date():
            return self._pop_pending(quote.ticker)

        self._latest_quotes[quote.ticker] = quote

        # Only evaluate the spread after we have both quotes and we're on the second symbol.
        if quote.ticker == self._pair[-1]:
            self._maybe_refresh_history(timestamp)
            spread_info = self._update_spread(timestamp)
            if spread_info is not None:
                _, z_score = spread_info
                new_signals = self._evaluate_signals(z_score, timestamp)
                for signal in new_signals:
                    self._pending_signals[signal.ticker].append(signal)

        return self._pop_pending(quote.ticker)

    def diagnostics(self, *, timestamp: datetime) -> StrategyDiagnostics:
        metrics = {}
        for ticker in self._pair:
            metrics[ticker] = {
                "z_score": self._latest_zscore if self._latest_zscore is not None else float("nan"),
                "spread": self._latest_spread if self._latest_spread is not None else float("nan"),
                "mean": self._latest_mean if self._latest_mean is not None else float("nan"),
                "std": self._latest_std if self._latest_std is not None else float("nan"),
            }
        active_positions = {}
        for idx, ticker in enumerate(self._pair):
            if not self._position.active or not self._position.direction:
                active_positions[ticker] = False
            else:
                active_positions[ticker] = (
                    (self._position.direction == "long_a" and idx == 0)
                    or (self._position.direction == "long_b" and idx == 1)
                )
        extras = {
            "direction": self._position.direction,
            "cooldown_until": self._cooldown_until.isoformat() if self._cooldown_until else None,
        }
        return StrategyDiagnostics(
            timestamp=timestamp,
            regime=None,
            target_ticker=None,
            active_positions=active_positions,
            latest_metrics=metrics,
            flattened_today=self._flattened_date == timestamp.date(),
            extras=extras,
        )

    # --- Internal helpers -------------------------------------------------

    def _pop_pending(self, ticker: str) -> Signal | None:
        queue = self._pending_signals.get(ticker)
        if queue:
            return queue.pop(0)
        return None

    def _maybe_refresh_history(self, timestamp: datetime) -> None:
        if self._history_loaded_date == timestamp.date():
            return

        interval = self._params.interval
        span = "day"
        frames: dict[str, pd.Series] = {}

        for ticker in self._pair:
            try:
                frame = self._data_service.historical_dataframe(ticker, span=span, interval=interval)
            except ValueError:
                frame = pd.DataFrame()
            if frame.empty or "close_price" not in frame.columns:
                continue
            series = frame["close_price"].astype(float)
            frames[ticker] = series

        if len(frames) != 2:
            return

        combined = pd.concat(frames, axis=1).dropna()
        if combined.empty:
            return

        prices_a = combined[self._pair[0]]
        prices_b = combined[self._pair[1]]
        log_spread = (prices_a.apply(lambda x: math.log(x) if x > 0 else float("nan"))
                      - prices_b.apply(lambda x: math.log(x) if x > 0 else float("nan")))
        log_spread = log_spread.dropna()
        if log_spread.empty:
            return

        tail_values = log_spread.tail(self._params.lookback_bars).tolist()
        if len(tail_values) < 5:
            return
        self._spread_window.clear()
        self._spread_window.extend(tail_values)
        self._history_loaded_date = timestamp.date()
        self._latest_mean = sum(self._spread_window) / len(self._spread_window)
        self._latest_std = self._compute_std(self._spread_window, self._latest_mean)
        self._latest_spread = self._spread_window[-1]
        self._latest_zscore = self._compute_zscore(self._latest_spread, self._latest_mean, self._latest_std)

    def _update_spread(self, timestamp: datetime) -> tuple[float, float] | None:
        if len(self._latest_quotes) < 2:
            return None
        quote_a = self._latest_quotes.get(self._pair[0])
        quote_b = self._latest_quotes.get(self._pair[1])
        if not quote_a or not quote_b:
            return None
        if quote_a.price <= 0 or quote_b.price <= 0:
            return None
        if self._last_spread_timestamp and timestamp <= self._last_spread_timestamp:
            return None

        spread = math.log(quote_a.price) - math.log(quote_b.price)
        self._spread_window.append(spread)
        if len(self._spread_window) < 5:
            return None

        mean = sum(self._spread_window) / len(self._spread_window)
        std = self._compute_std(self._spread_window, mean)
        z_score = self._compute_zscore(spread, mean, std)

        self._latest_mean = mean
        self._latest_std = std
        self._latest_spread = spread
        self._latest_zscore = z_score
        self._last_spread_timestamp = timestamp
        return spread, z_score

    def _evaluate_signals(self, z_score: float | None, timestamp: datetime) -> list[Signal]:
        if z_score is None:
            return []

        if self._position.active:
            return self._maybe_exit(z_score, timestamp)
        return self._maybe_enter(z_score, timestamp)

    def _maybe_enter(self, z_score: float, timestamp: datetime) -> list[Signal]:
        if len(self._spread_window) < self._params.lookback_bars:
            return []
        if self._cooldown_until and timestamp < self._cooldown_until:
            return []

        # Time-of-day filter: Avoid first 30 minutes (high volatility, wide spreads)
        # and last 30 minutes (closing auctions, unpredictable)
        current_time = timestamp.time()
        market_open = self._config.trading_window.market_open
        market_close = self._config.trading_window.market_close

        from datetime import time as time_class
        avoid_start = time_class(market_open.hour, market_open.minute + 30)
        avoid_end = time_class(market_close.hour, market_close.minute - 30) if market_close.minute >= 30 else time_class(market_close.hour - 1, 60 + market_close.minute - 30)

        if current_time < avoid_start or current_time > avoid_end:
            return []  # Don't trade during volatile opening/closing periods

        entry = self._params.entry_zscore
        signals: list[Signal] = []

        if z_score <= -entry:
            self._position.active = True
            self._position.direction = "long_a"
            self._position.entry_time = timestamp
            self._position.entry_zscore = z_score
            signals.extend(self._build_entry_signals(direction="long_a", z_score=z_score))
        elif z_score >= entry:
            self._position.active = True
            self._position.direction = "long_b"
            self._position.entry_time = timestamp
            self._position.entry_zscore = z_score
            signals.extend(self._build_entry_signals(direction="long_b", z_score=z_score))
        return signals

    def _maybe_exit(self, z_score: float, timestamp: datetime) -> list[Signal]:
        if not self._position.active or not self._position.direction:
            return []
        signals: list[Signal] = []
        exit_threshold = self._params.exit_zscore
        reason: str | None = None

        if self._position.entry_time:
            held = timestamp - self._position.entry_time
            if held >= timedelta(minutes=self._params.max_hold_minutes):
                reason = "time_stop"

        if reason is None:
            if self._position.direction == "long_a" and z_score >= -exit_threshold:
                reason = "mean_revert"
            elif self._position.direction == "long_b" and z_score <= exit_threshold:
                reason = "mean_revert"

        if reason:
            signals.extend(self._build_exit_signals(reason=reason, z_score=z_score))
            self._cooldown_until = timestamp + timedelta(minutes=self._params.cooldown_minutes)
            self._position.reset()
        return signals

    def _build_entry_signals(self, *, direction: str, z_score: float) -> list[Signal]:
        if direction == "long_a":
            metadata = {"reason": "pair_long_a_entry", "z_score": z_score, "target": self._pair[0]}
            return [
                Signal(ticker=self._pair[1], side="flat", metadata=metadata),
                Signal(ticker=self._pair[0], side="buy", metadata=metadata),
            ]
        metadata = {"reason": "pair_long_b_entry", "z_score": z_score, "target": self._pair[1]}
        return [
            Signal(ticker=self._pair[0], side="flat", metadata=metadata),
            Signal(ticker=self._pair[1], side="buy", metadata=metadata),
        ]

    def _build_exit_signals(self, *, reason: str, z_score: float) -> list[Signal]:
        metadata = {"reason": f"pair_exit_{reason}", "z_score": z_score}
        if self._position.direction == "long_a":
            return [Signal(ticker=self._pair[0], side="flat", metadata=metadata)]
        if self._position.direction == "long_b":
            return [Signal(ticker=self._pair[1], side="flat", metadata=metadata)]
        return []

    @staticmethod
    def _compute_std(values: deque[float], mean: float) -> float | None:
        if not values:
            return None
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        if variance <= 0:
            return None
        return math.sqrt(variance)

    @staticmethod
    def _compute_zscore(value: float, mean: float | None, std: float | None) -> float | None:
        if mean is None or std is None or std == 0:
            return None
        return (value - mean) / std
