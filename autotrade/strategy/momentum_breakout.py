"""Momentum breakout strategy for strong trending markets.

Best for: Strong bull or bear markets with high momentum
Entry: Price breaks above resistance with volume confirmation
Exit: Momentum fades or trend reverses

This strategy captures explosive moves in strong trending markets.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from autotrade.analysis.market_regime import (
    MarketRegime,
    TrendStrength,
    VolatilityRegime,
)
from autotrade.data.market import MarketData
from autotrade.strategy.base import Signal, Strategy, SignalType

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class MomentumBreakoutParams:
    """Momentum breakout strategy parameters."""

    lookback_period: int = 20  # Period for high/low identification
    volume_multiplier: float = 1.5  # Volume must be 1.5x average
    atr_period: int = 14  # ATR calculation period
    atr_stop_multiplier: float = 2.0  # Stop loss distance
    min_price: float = 10.0  # Minimum stock price
    min_volume: int = 2_000_000  # Minimum average daily volume
    momentum_threshold: float = 5.0  # Minimum % gain over lookback period


class MomentumBreakoutStrategy(Strategy):
    """
    Momentum breakout strategy for explosive moves.

    Entry Conditions (LONG):
    1. Market regime: Strong uptrend or high volatility bull market
    2. Price breaks above 20-day high
    3. Volume > 1.5x average volume (confirmation)
    4. Strong momentum: +5% or more over lookback period
    5. Price > $10 (avoid penny stocks)

    Exit Conditions:
    1. Price crosses below 10-day moving average
    2. ATR-based trailing stop (2x ATR)
    3. Volume dries up (< 0.7x average)
    4. Maximum hold: 10 days (momentum trades don't last forever)
    """

    def __init__(self, params: MomentumBreakoutParams):
        """Initialize strategy."""
        self.name = "momentum_breakout"
        self.params = params
        self._indicators: dict[str, dict] = {}

    def is_compatible_with_regime(self, regime: MarketRegime) -> bool:
        """
        Check if strategy is compatible with current market regime.

        Momentum breakout works best in strong trending markets.
        """
        # Perfect for strong trends
        if regime.trend_strength == TrendStrength.STRONG_TREND:
            return True

        # Good in high volatility (can catch explosive moves)
        if regime.volatility == VolatilityRegime.HIGH and regime.is_bullish():
            return True

        # Avoid ranging markets (false breakouts)
        if regime.trend_strength == TrendStrength.RANGING:
            return False

        return False

    def calculate_indicators(self, ticker: str, data: MarketData) -> dict:
        """Calculate momentum and breakout indicators."""
        df = pd.DataFrame(
            {
                "close": data.close_price,
                "high": data.high_price,
                "low": data.low_price,
                "volume": data.volume,
            }
        )

        # 20-day high/low
        high_20 = df["high"].rolling(window=self.params.lookback_period).max()
        low_20 = df["low"].rolling(window=self.params.lookback_period).min()

        # Moving averages
        sma_10 = df["close"].rolling(window=10).mean()
        sma_50 = df["close"].rolling(window=50).mean()

        # Volume
        avg_volume = df["volume"].rolling(window=20).mean()

        # ATR
        atr = self._calculate_atr(df, self.params.atr_period)

        # Momentum (% change over lookback period)
        momentum_pct = (
            (df["close"] - df["close"].shift(self.params.lookback_period))
            / df["close"].shift(self.params.lookback_period)
            * 100
        )

        indicators = {
            "high_20": high_20.iloc[-1] if len(high_20) > 0 else None,
            "low_20": low_20.iloc[-1] if len(low_20) > 0 else None,
            "sma_10": sma_10.iloc[-1] if len(sma_10) > 0 else None,
            "sma_50": sma_50.iloc[-1] if len(sma_50) > 0 else None,
            "avg_volume": avg_volume.iloc[-1] if len(avg_volume) > 0 else None,
            "atr": atr.iloc[-1] if len(atr) > 0 else None,
            "momentum_pct": momentum_pct.iloc[-1] if len(momentum_pct) > 0 else None,
            "current_volume": df["volume"].iloc[-1] if len(df) > 0 else 0,
        }

        self._indicators[ticker] = indicators
        return indicators

    def generate_signals(
        self,
        ticker: str,
        data: MarketData,
        regime: MarketRegime | None = None,
    ) -> list[Signal]:
        """Generate momentum breakout signals."""
        signals = []

        # Check regime compatibility
        if regime and not self.is_compatible_with_regime(regime):
            _LOG.debug(
                "%s: Regime not compatible (%s) - skipping momentum breakout",
                ticker,
                regime,
            )
            return signals

        # Calculate indicators
        indicators = self.calculate_indicators(ticker, data)

        price = data.close_price[-1]
        high_20 = indicators["high_20"]
        sma_50 = indicators["sma_50"]
        avg_volume = indicators["avg_volume"]
        current_volume = indicators["current_volume"]
        momentum_pct = indicators["momentum_pct"]
        atr = indicators["atr"]

        # Validate indicators
        if any(
            x is None for x in [high_20, sma_50, avg_volume, momentum_pct, atr]
        ):
            return signals

        # Price and volume filters
        if price < self.params.min_price:
            return signals

        if avg_volume < self.params.min_volume:
            return signals

        # Check for breakout
        volume_confirmed = current_volume >= (
            avg_volume * self.params.volume_multiplier
        )
        momentum_strong = momentum_pct >= self.params.momentum_threshold
        breakout = price >= high_20 * 0.999  # Within 0.1% of 20-day high

        # LONG Entry: Momentum breakout
        if breakout and volume_confirmed and momentum_strong and price > sma_50:
            stop_price = price - (atr * self.params.atr_stop_multiplier)

            signals.append(
                Signal(
                    ticker=ticker,
                    signal_type=SignalType.ENTRY,
                    direction="long",
                    price=price,
                    confidence=0.80,
                    metadata={
                        "strategy": self.name,
                        "reason": "momentum_breakout",
                        "momentum_pct": momentum_pct,
                        "volume_ratio": current_volume / avg_volume,
                        "breakout_level": high_20,
                        "stop_price": stop_price,
                    },
                )
            )
            _LOG.info(
                "%s: LONG signal - Momentum breakout (Price=%.2f, Momentum=%.1f%%, Vol Ratio=%.1fx)",
                ticker,
                price,
                momentum_pct,
                current_volume / avg_volume,
            )

        return signals

    def check_exit_conditions(
        self,
        ticker: str,
        entry_price: float,
        current_price: float,
        direction: str,
        days_held: int,
    ) -> tuple[bool, str | None]:
        """Check if position should be exited."""
        indicators = self._indicators.get(ticker, {})
        sma_10 = indicators.get("sma_10")
        atr = indicators.get("atr")
        avg_volume = indicators.get("avg_volume")
        current_volume = indicators.get("current_volume")

        # Exit 1: Trend reversal (price below 10 MA)
        if sma_10 and current_price < sma_10:
            return True, "trend_reversal"

        # Exit 2: ATR trailing stop
        if atr:
            stop_price = entry_price - (atr * self.params.atr_stop_multiplier)
            if current_price < stop_price:
                return True, "stop_loss"

        # Exit 3: Volume dries up (momentum fading)
        if avg_volume and current_volume:
            if current_volume < avg_volume * 0.7:
                return True, "volume_dryup"

        # Exit 4: Maximum hold time (momentum doesn't last forever)
        if days_held >= 10:
            return True, "max_hold_time"

        return False, None

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range."""
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift())
        low_close = abs(df["low"] - df["close"].shift())

        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)

        atr = true_range.rolling(window=period).mean()

        return atr
