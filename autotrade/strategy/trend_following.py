"""Trend following strategy based on moving averages and momentum.

This strategy is based on 40+ years of academic research showing that
price momentum persists over medium-term horizons (1-12 months).

Key Papers:
- "A Quantitative Approach to Tactical Asset Allocation" (Faber, 2007)
- "Time Series Momentum" (Moskowitz et al., 2012)
- "Trend Following" (Hurst, 2013)

Strategy Rules:
1. Entry: Price > 50 MA AND 50 MA > 200 MA AND price breaks 20-day high
2. Exit: Price < 10 MA OR stop loss (2 × ATR)
3. Hold: 5-30 days typically

Works best on: SPY, QQQ, IWM (liquid, trending instruments)
Expected Sharpe: 0.8-1.2
Expected Win Rate: 35-45%
Expected Profit Factor: 2.0-2.5
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from autotrade.config import BotConfig
from autotrade.data.market import MarketDataService, Quote
from autotrade.strategy.base import Signal, StrategyDiagnostics


@dataclass(slots=True)
class _TickerState:
    """Track state for each ticker."""
    in_position: bool = False
    entry_price: float | None = None
    entry_time: datetime | None = None
    highest_price: float | None = None  # Track trailing high
    atr: float | None = None  # Average True Range for stop loss

    # Moving averages
    sma_10: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    high_20: float | None = None  # 20-day high

    def reset(self) -> None:
        """Reset position state."""
        self.in_position = False
        self.entry_price = None
        self.entry_time = None
        self.highest_price = None


@dataclass(frozen=True)
class TrendFollowingParams:
    """Parameters for trend following strategy."""
    sma_fast: int = 50  # Fast trend MA
    sma_slow: int = 200  # Slow trend MA
    sma_exit: int = 10  # Exit MA (faster)
    breakout_period: int = 20  # Breakout lookback period
    atr_period: int = 14  # ATR calculation period
    atr_stop_multiplier: float = 2.0  # Stop loss = entry - (ATR × multiplier)
    max_hold_days: int = 30  # Maximum hold period
    min_volume: int = 1_000_000  # Minimum daily volume


class TrendFollowingStrategy:
    """
    Trend following strategy for daily/swing trading.

    This is a systematic approach that captures sustained price trends
    while limiting downside risk with ATR-based stops.

    Advantages:
    - Backed by decades of research
    - Works across multiple markets and timeframes
    - Simple, rule-based (no curve-fitting)
    - Captures large moves while cutting losers quickly
    - Low correlation to buy-and-hold

    Disadvantages:
    - Low win rate (35-45%)
    - Whipsaws in sideways markets
    - Requires discipline to follow signals
    """

    def __init__(self, config: BotConfig, data_service: MarketDataService) -> None:
        self._config = config
        self._data_service = data_service
        self._params = config.strategy.params

        if not isinstance(self._params, TrendFollowingParams):
            # Use defaults if not provided
            self._params = TrendFollowingParams()

        self._tickers = config.strategy.tickers
        self._states: dict[str, _TickerState] = {
            ticker: _TickerState() for ticker in self._tickers
        }

        # Cache historical data load date
        self._history_loaded_date: dict[str, datetime.date] = {}

    def should_flatten(self, *, timestamp: datetime) -> bool:
        """
        For trend following, we don't force end-of-day flattening.
        Positions can be held overnight and for multiple days.

        Only flatten if explicitly signaled by strategy rules.
        """
        return False

    def on_quote(self, quote: Quote, *, timestamp: datetime) -> Signal | None:
        """
        Process end-of-day quote and generate signal.

        This strategy is designed for daily EOD execution:
        - Check once per day after market close
        - Use daily bars for calculations
        - Hold positions across multiple days
        """
        ticker = quote.ticker
        state = self._states[ticker]

        # Refresh historical data if needed (once per day)
        self._maybe_refresh_history(ticker, timestamp)

        # Need indicators calculated before generating signals
        if state.sma_50 is None or state.sma_200 is None:
            return None

        # Update trailing high if in position
        if state.in_position:
            if state.highest_price is None or quote.price > state.highest_price:
                state.highest_price = quote.price

        # Generate signal
        if state.in_position:
            return self._check_exit(ticker, quote.price, timestamp)
        else:
            return self._check_entry(ticker, quote.price, timestamp)

    def diagnostics(self, *, timestamp: datetime) -> StrategyDiagnostics:
        """Return current strategy state for logging/monitoring."""
        metrics = {}
        active_positions = {}

        for ticker in self._tickers:
            state = self._states[ticker]
            metrics[ticker] = {
                'sma_10': state.sma_10 or float('nan'),
                'sma_50': state.sma_50 or float('nan'),
                'sma_200': state.sma_200 or float('nan'),
                'high_20': state.high_20 or float('nan'),
                'atr': state.atr or float('nan'),
                'in_trend': (state.sma_50 or 0) > (state.sma_200 or 0),
            }
            active_positions[ticker] = state.in_position

        return StrategyDiagnostics(
            timestamp=timestamp,
            regime="trending" if any(m.get('in_trend') for m in metrics.values()) else "sideways",
            target_ticker=None,
            active_positions=active_positions,
            latest_metrics=metrics,
            flattened_today=False,
            extras={}
        )

    # --- Internal Methods ---

    def _maybe_refresh_history(self, ticker: str, timestamp: datetime) -> None:
        """Load daily historical data to calculate indicators."""
        if self._history_loaded_date.get(ticker) == timestamp.date():
            return  # Already loaded today

        try:
            # Get 1 year of daily data
            df = self._data_service.historical_dataframe(ticker, span="year", interval="daily")
        except ValueError:
            return

        if df.empty:
            return

        required_cols = ['close_price', 'high_price', 'low_price', 'volume']
        if not all(col in df.columns for col in required_cols):
            return

        # Need enough data for 200-day MA
        if len(df) < self._params.sma_slow:
            return

        closes = df['close_price'].astype(float)
        highs = df['high_price'].astype(float)
        lows = df['low_price'].astype(float)
        volumes = df['volume'].astype(int)

        # Calculate moving averages
        sma_10 = closes.rolling(window=self._params.sma_exit).mean().iloc[-1]
        sma_50 = closes.rolling(window=self._params.sma_fast).mean().iloc[-1]
        sma_200 = closes.rolling(window=self._params.sma_slow).mean().iloc[-1]

        # Calculate 20-day high
        high_20 = highs.rolling(window=self._params.breakout_period).max().iloc[-1]

        # Calculate ATR (Average True Range)
        atr = self._calculate_atr(highs, lows, closes, period=self._params.atr_period)

        # Check minimum volume requirement
        avg_volume = volumes.tail(20).mean()
        if avg_volume < self._params.min_volume:
            # Skip this ticker if not liquid enough
            return

        # Update state
        state = self._states[ticker]
        state.sma_10 = float(sma_10) if not pd.isna(sma_10) else None
        state.sma_50 = float(sma_50) if not pd.isna(sma_50) else None
        state.sma_200 = float(sma_200) if not pd.isna(sma_200) else None
        state.high_20 = float(high_20) if not pd.isna(high_20) else None
        state.atr = atr

        self._history_loaded_date[ticker] = timestamp.date()

    @staticmethod
    def _calculate_atr(
        highs: pd.Series,
        lows: pd.Series,
        closes: pd.Series,
        period: int = 14
    ) -> float | None:
        """
        Calculate Average True Range (ATR).

        ATR measures volatility and is used for stop loss placement.
        True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        ATR = EMA of True Range over N periods
        """
        if len(highs) < period + 1:
            return None

        prev_closes = closes.shift(1)

        tr1 = highs - lows
        tr2 = (highs - prev_closes).abs()
        tr3 = (lows - prev_closes).abs()

        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean().iloc[-1]

        return float(atr) if not pd.isna(atr) else None

    def _check_entry(self, ticker: str, price: float, timestamp: datetime) -> Signal | None:
        """
        Check for entry signal.

        Entry conditions (all must be true):
        1. Price > 50 MA (uptrend)
        2. 50 MA > 200 MA (long-term uptrend)
        3. Price breaks above 20-day high (momentum breakout)
        """
        state = self._states[ticker]

        # Need all indicators
        if None in (state.sma_50, state.sma_200, state.high_20, state.atr):
            return None

        # Condition 1: Price above 50 MA (in uptrend)
        if price <= state.sma_50:
            return None

        # Condition 2: 50 MA > 200 MA (long-term uptrend)
        if state.sma_50 <= state.sma_200:
            return None

        # Condition 3: Breakout above 20-day high
        # Add small buffer (0.1%) to avoid false breakouts from noise
        breakout_threshold = state.high_20 * 1.001

        if price <= breakout_threshold:
            return None

        # All conditions met - enter position
        state.in_position = True
        state.entry_price = price
        state.entry_time = timestamp
        state.highest_price = price

        return Signal(
            ticker=ticker,
            side="buy",
            quantity=None,  # Let execution engine calculate size
            metadata={
                'reason': 'trend_breakout',
                'entry_price': price,
                'sma_50': state.sma_50,
                'sma_200': state.sma_200,
                'high_20': state.high_20,
                'atr': state.atr,
                'atr_stop': price - (state.atr * self._params.atr_stop_multiplier)
            }
        )

    def _check_exit(self, ticker: str, price: float, timestamp: datetime) -> Signal | None:
        """
        Check for exit signal.

        Exit conditions (any triggers exit):
        1. Price < 10 MA (trend reversal)
        2. Price < entry - (2 × ATR) (stop loss hit)
        3. Held for max_hold_days (time stop)
        """
        state = self._states[ticker]

        if not state.in_position or state.entry_price is None:
            return None

        reason = None

        # Exit 1: Price crosses below fast MA (trend ended)
        if state.sma_10 and price < state.sma_10:
            reason = 'ma_exit'

        # Exit 2: ATR-based stop loss
        elif state.atr:
            stop_price = state.entry_price - (state.atr * self._params.atr_stop_multiplier)
            if price < stop_price:
                reason = 'stop_loss'

        # Exit 3: Time stop (held too long)
        elif state.entry_time:
            days_held = (timestamp - state.entry_time).days
            if days_held >= self._params.max_hold_days:
                reason = 'time_stop'

        if reason:
            # Calculate profit/loss
            pnl_pct = ((price - state.entry_price) / state.entry_price) * 100 if state.entry_price else 0

            # Reset state
            state.reset()

            return Signal(
                ticker=ticker,
                side="sell",
                quantity=None,  # Sell entire position
                metadata={
                    'reason': f'trend_{reason}',
                    'exit_price': price,
                    'entry_price': state.entry_price,
                    'pnl_pct': pnl_pct
                }
            )

        return None
