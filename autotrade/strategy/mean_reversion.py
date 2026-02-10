"""Mean reversion strategy for ranging markets.

Best for: Neutral/ranging markets with low-medium volatility
Entry: Price deviates from mean (oversold/overbought)
Exit: Price returns to mean

This strategy profits from market inefficiencies when prices
temporarily deviate from their average and then revert.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from autotrade.analysis.market_regime import (
    MarketRegime,
    TrendDirection,
    TrendStrength,
)
from autotrade.data.market import MarketData
from autotrade.strategy.base import Signal, Strategy, SignalType

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class MeanReversionParams:
    """Mean reversion strategy parameters."""

    lookback_period: int = 20  # Bollinger Band period
    num_std: float = 2.0  # Number of standard deviations
    rsi_period: int = 14  # RSI period
    rsi_oversold: float = 30.0  # RSI oversold threshold
    rsi_overbought: float = 70.0  # RSI overbought threshold
    min_volume: int = 1_000_000  # Minimum daily volume
    profit_target_pct: float = 2.0  # Take profit at 2%
    stop_loss_pct: float = 3.0  # Stop loss at 3%


class MeanReversionStrategy(Strategy):
    """
    Mean reversion strategy using Bollinger Bands + RSI.

    Entry Conditions (LONG):
    1. Market regime: Ranging or Neutral (NOT strong trending)
    2. Price touches or crosses below lower Bollinger Band
    3. RSI < 30 (oversold)
    4. Volume > minimum threshold

    Entry Conditions (SHORT):
    1. Market regime: Ranging or Neutral
    2. Price touches or crosses above upper Bollinger Band
    3. RSI > 70 (overbought)
    4. Volume > minimum threshold

    Exit Conditions:
    1. Price returns to middle band (20 SMA)
    2. Profit target hit (+2%)
    3. Stop loss hit (-3%)
    4. Regime change to strong trending
    """

    def __init__(self, params: MeanReversionParams):
        """Initialize strategy."""
        self.name = "mean_reversion"
        self.params = params
        self._indicators: dict[str, dict] = {}

    def is_compatible_with_regime(self, regime: MarketRegime) -> bool:
        """
        Check if strategy is compatible with current market regime.

        Mean reversion works best in ranging/choppy markets.
        Avoid in strong trending markets (will get run over).
        """
        # Prefer ranging markets
        if regime.trend_strength == TrendStrength.RANGING:
            return True

        # Accept neutral/weak trends
        if regime.trend_direction == TrendDirection.NEUTRAL:
            return True

        # Avoid strong trends
        if regime.trend_strength == TrendStrength.STRONG_TREND:
            return False

        return True

    def calculate_indicators(self, ticker: str, data: MarketData) -> dict:
        """Calculate Bollinger Bands and RSI."""
        df = pd.DataFrame(
            {
                "close": data.close_price,
                "volume": data.volume,
            }
        )

        # Bollinger Bands
        sma = df["close"].rolling(window=self.params.lookback_period).mean()
        std = df["close"].rolling(window=self.params.lookback_period).std()
        upper_band = sma + (self.params.num_std * std)
        lower_band = sma - (self.params.num_std * std)

        # RSI
        rsi = self._calculate_rsi(df["close"], self.params.rsi_period)

        indicators = {
            "sma": sma.iloc[-1] if len(sma) > 0 else None,
            "upper_band": upper_band.iloc[-1] if len(upper_band) > 0 else None,
            "lower_band": lower_band.iloc[-1] if len(lower_band) > 0 else None,
            "rsi": rsi.iloc[-1] if len(rsi) > 0 else None,
            "volume": df["volume"].iloc[-1] if len(df) > 0 else 0,
        }

        self._indicators[ticker] = indicators
        return indicators

    def generate_signals(
        self,
        ticker: str,
        data: MarketData,
        regime: MarketRegime | None = None,
    ) -> list[Signal]:
        """Generate mean reversion signals."""
        signals = []

        # Check regime compatibility
        if regime and not self.is_compatible_with_regime(regime):
            _LOG.debug(
                "%s: Regime not compatible (%s) - skipping mean reversion",
                ticker,
                regime,
            )
            return signals

        # Calculate indicators
        indicators = self.calculate_indicators(ticker, data)

        price = data.close_price[-1]
        upper_band = indicators["upper_band"]
        lower_band = indicators["lower_band"]
        sma = indicators["sma"]
        rsi = indicators["rsi"]
        volume = indicators["volume"]

        # Validate indicators
        if any(x is None for x in [upper_band, lower_band, sma, rsi]):
            return signals

        if volume < self.params.min_volume:
            return signals

        # LONG Entry: Oversold
        if price <= lower_band and rsi <= self.params.rsi_oversold:
            signals.append(
                Signal(
                    ticker=ticker,
                    signal_type=SignalType.ENTRY,
                    direction="long",
                    price=price,
                    confidence=0.75,
                    metadata={
                        "strategy": self.name,
                        "reason": "oversold_mean_reversion",
                        "rsi": rsi,
                        "bb_position": "below_lower_band",
                        "target_price": price * (1 + self.params.profit_target_pct / 100),
                        "stop_price": price * (1 - self.params.stop_loss_pct / 100),
                    },
                )
            )
            _LOG.info(
                "%s: LONG signal - Oversold (Price=%.2f, RSI=%.1f, Lower Band=%.2f)",
                ticker,
                price,
                rsi,
                lower_band,
            )

        # SHORT Entry: Overbought (if shorting enabled)
        elif price >= upper_band and rsi >= self.params.rsi_overbought:
            signals.append(
                Signal(
                    ticker=ticker,
                    signal_type=SignalType.ENTRY,
                    direction="short",
                    price=price,
                    confidence=0.75,
                    metadata={
                        "strategy": self.name,
                        "reason": "overbought_mean_reversion",
                        "rsi": rsi,
                        "bb_position": "above_upper_band",
                        "target_price": price * (1 - self.params.profit_target_pct / 100),
                        "stop_price": price * (1 + self.params.stop_loss_pct / 100),
                    },
                )
            )
            _LOG.info(
                "%s: SHORT signal - Overbought (Price=%.2f, RSI=%.1f, Upper Band=%.2f)",
                ticker,
                price,
                rsi,
                upper_band,
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
        sma = indicators.get("sma")

        if sma is None:
            return False, None

        # Exit 1: Price returned to mean
        if direction == "long" and current_price >= sma:
            return True, "return_to_mean"
        elif direction == "short" and current_price <= sma:
            return True, "return_to_mean"

        # Exit 2: Profit target
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        if direction == "long":
            if pnl_pct >= self.params.profit_target_pct:
                return True, "profit_target"
        elif direction == "short":
            if pnl_pct <= -self.params.profit_target_pct:
                return True, "profit_target"

        # Exit 3: Stop loss
        if direction == "long":
            if pnl_pct <= -self.params.stop_loss_pct:
                return True, "stop_loss"
        elif direction == "short":
            if pnl_pct >= self.params.stop_loss_pct:
                return True, "stop_loss"

        return False, None

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = prices.diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi
