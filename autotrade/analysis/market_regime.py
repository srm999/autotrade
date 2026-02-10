"""Market regime detection for strategy selection.

Identifies market conditions to activate appropriate strategies:
- Trend direction: Bull, Bear, Neutral
- Trend strength: Strong trend vs Ranging
- Volatility: High, Medium, Low
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

_LOG = logging.getLogger(__name__)


class TrendDirection(Enum):
    """Market trend direction."""

    BULL = "bull"  # Sustained uptrend
    BEAR = "bear"  # Sustained downtrend
    NEUTRAL = "neutral"  # No clear direction


class TrendStrength(Enum):
    """Market trend strength."""

    STRONG_TREND = "strong_trend"  # Clear directional movement
    WEAK_TREND = "weak_trend"  # Some direction but choppy
    RANGING = "ranging"  # Sideways / mean reverting


class VolatilityRegime(Enum):
    """Market volatility level."""

    HIGH = "high"  # VIX > 25, large swings
    MEDIUM = "medium"  # VIX 15-25, normal
    LOW = "low"  # VIX < 15, calm


@dataclass(frozen=True)
class MarketRegime:
    """Complete market regime classification."""

    trend_direction: TrendDirection
    trend_strength: TrendStrength
    volatility: VolatilityRegime

    # Supporting metrics
    sma_50: float
    sma_200: float
    atr: float
    adx: float  # Average Directional Index
    vix: float | None = None

    def __str__(self) -> str:
        """Human-readable regime description."""
        return (
            f"{self.trend_direction.value.upper()} "
            f"{self.trend_strength.value.replace('_', ' ').title()} "
            f"({self.volatility.value.title()} Vol)"
        )

    def is_trending(self) -> bool:
        """Check if market is trending."""
        return self.trend_strength in (TrendStrength.STRONG_TREND, TrendStrength.WEAK_TREND)

    def is_ranging(self) -> bool:
        """Check if market is ranging/choppy."""
        return self.trend_strength == TrendStrength.RANGING

    def is_bullish(self) -> bool:
        """Check if market is bullish."""
        return self.trend_direction == TrendDirection.BULL

    def is_bearish(self) -> bool:
        """Check if market is bearish."""
        return self.trend_direction == TrendDirection.BEAR


class MarketRegimeDetector:
    """Detects market regime for strategy selection."""

    def __init__(self):
        """Initialize detector."""
        self._current_regime: MarketRegime | None = None

    def detect_regime(
        self,
        prices: pd.Series,
        vix: float | None = None,
    ) -> MarketRegime:
        """
        Detect current market regime from price data.

        Args:
            prices: Series of close prices (indexed by date)
            vix: Optional VIX level for volatility assessment

        Returns:
            MarketRegime classification
        """
        if len(prices) < 200:
            raise ValueError("Need at least 200 days of price data for regime detection")

        # Calculate indicators - ensure scalar float values
        sma_50 = float(prices.rolling(window=50).mean().iloc[-1])
        sma_200 = float(prices.rolling(window=200).mean().iloc[-1])

        # Calculate ATR (Average True Range)
        high = prices.rolling(window=1).max()  # Simplified - use actual high if available
        low = prices.rolling(window=1).min()  # Simplified - use actual low if available
        atr = self._calculate_atr(prices, high, low, period=14)

        # Calculate ADX (Average Directional Index)
        adx = self._calculate_adx(prices, period=14)

        # Determine trend direction
        current_price = float(prices.iloc[-1])
        trend_direction = self._classify_trend_direction(current_price, sma_50, sma_200)

        # Determine trend strength
        trend_strength = self._classify_trend_strength(adx, prices)

        # Determine volatility regime
        volatility = self._classify_volatility(atr, current_price, vix)

        regime = MarketRegime(
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            volatility=volatility,
            sma_50=sma_50,
            sma_200=sma_200,
            atr=atr,
            adx=adx,
            vix=vix,
        )

        self._current_regime = regime
        _LOG.info("Market Regime: %s (ADX=%.1f, ATR=%.2f)", regime, adx, atr)

        return regime

    def _classify_trend_direction(
        self,
        price: float,
        sma_50: float,
        sma_200: float,
    ) -> TrendDirection:
        """Classify trend direction using moving averages."""
        if price > sma_50 and sma_50 > sma_200:
            # Price above both MAs, 50 above 200 (golden cross)
            return TrendDirection.BULL
        elif price < sma_50 and sma_50 < sma_200:
            # Price below both MAs, 50 below 200 (death cross)
            return TrendDirection.BEAR
        else:
            # Mixed signals
            return TrendDirection.NEUTRAL

    def _classify_trend_strength(
        self,
        adx: float,
        prices: pd.Series,
    ) -> TrendStrength:
        """
        Classify trend strength using ADX.

        ADX Interpretation:
        - > 25: Strong trend
        - 20-25: Weak trend
        - < 20: Ranging/choppy
        """
        if adx > 25:
            return TrendStrength.STRONG_TREND
        elif adx > 20:
            return TrendStrength.WEAK_TREND
        else:
            return TrendStrength.RANGING

    def _classify_volatility(
        self,
        atr: float,
        price: float,
        vix: float | None,
    ) -> VolatilityRegime:
        """
        Classify volatility regime.

        Uses ATR% (ATR as percentage of price) and VIX if available.
        """
        atr_pct = (atr / price) * 100

        # VIX-based classification (if available)
        if vix is not None:
            if vix > 25:
                return VolatilityRegime.HIGH
            elif vix > 15:
                return VolatilityRegime.MEDIUM
            else:
                return VolatilityRegime.LOW

        # ATR%-based classification
        if atr_pct > 2.5:
            return VolatilityRegime.HIGH
        elif atr_pct > 1.5:
            return VolatilityRegime.MEDIUM
        else:
            return VolatilityRegime.LOW

    def _calculate_atr(
        self,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series,
        period: int = 14,
    ) -> float:
        """
        Calculate Average True Range.

        Simplified version using close prices if high/low not available.
        """
        # Calculate true range (simplified using close-to-close changes)
        tr = close.diff().abs()

        # Calculate ATR as moving average of true range
        atr = tr.rolling(window=period).mean().iloc[-1]

        # Return default if calculation fails
        if pd.isna(atr) or np.isinf(atr):
            return float(close.iloc[-1] * 0.01)  # Default to 1% of price

        return float(atr)

    def _calculate_adx(
        self,
        prices: pd.Series,
        period: int = 14,
    ) -> float:
        """
        Calculate Average Directional Index (ADX).

        Simplified version using price momentum.
        ADX measures trend strength (0-100):
        - > 25: Strong trend
        - < 20: Weak/no trend
        """
        # Calculate directional movement
        delta = prices.diff()

        # Positive and negative directional movement
        plus_dm = delta.clip(lower=0)
        minus_dm = (-delta).clip(lower=0)

        # Smooth with moving average
        plus_dm_smooth = plus_dm.rolling(window=period).mean()
        minus_dm_smooth = minus_dm.rolling(window=period).mean()

        # Calculate directional indicators
        atr = prices.diff().abs().rolling(window=period).mean()

        # Avoid division by zero
        plus_di = 100 * (plus_dm_smooth / atr.replace(0, np.nan))
        minus_di = 100 * (minus_dm_smooth / atr.replace(0, np.nan))

        # Calculate DX (Directional Index)
        # Avoid division by zero in denominator
        di_sum = plus_di + minus_di
        di_diff = (plus_di - minus_di).abs()
        dx = 100 * (di_diff / di_sum.replace(0, np.nan))

        # ADX is smoothed DX
        adx = dx.rolling(window=period).mean().iloc[-1]

        # Return default if calculation fails (NaN or inf)
        if pd.isna(adx) or np.isinf(adx):
            return 20.0

        return float(adx)

    @property
    def current_regime(self) -> MarketRegime | None:
        """Get the most recently detected regime."""
        return self._current_regime
