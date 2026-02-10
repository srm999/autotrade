"""Real-time stock screener for finding trading opportunities.

Scans for technical setups across multiple strategies:
- High momentum stocks
- Oversold/overbought conditions
- Breakout candidates
- High relative volume
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScreenerCriteria:
    """Screening criteria for stocks."""

    min_price: float = 10.0  # Minimum stock price
    max_price: float = 500.0  # Maximum stock price
    min_volume: int = 1_000_000  # Minimum average daily volume
    min_dollar_volume: float = 10_000_000  # Minimum daily dollar volume

    # Momentum criteria
    min_momentum_pct: float = 3.0  # Minimum % gain over period
    momentum_period: int = 5  # Days for momentum calculation

    # Relative volume
    min_relative_volume: float = 1.3  # Current volume / Average volume

    # Volatility
    min_atr_pct: float = 1.0  # Minimum ATR as % of price
    max_atr_pct: float = 5.0  # Maximum ATR as % of price


@dataclass
class ScanResult:
    """Result from stock screening."""

    ticker: str
    price: float
    volume: int
    relative_volume: float
    momentum_pct: float
    atr_pct: float
    score: float  # Composite score (0-100)
    matched_criteria: list[str]
    timestamp: datetime


class StockScreener:
    """Real-time stock screener."""

    def __init__(self, criteria: ScreenerCriteria | None = None):
        """
        Initialize screener.

        Args:
            criteria: Screening criteria (uses defaults if None)
        """
        self.criteria = criteria or ScreenerCriteria()
        self._scan_cache: dict[str, ScanResult] = {}

    def scan_ticker(
        self,
        ticker: str,
        price_data: pd.DataFrame,
    ) -> ScanResult | None:
        """
        Scan a single ticker for opportunities.

        Args:
            ticker: Stock ticker symbol
            price_data: DataFrame with columns [date, open, high, low, close, volume]

        Returns:
            ScanResult if ticker meets criteria, None otherwise
        """
        if len(price_data) < 50:
            return None

        try:
            # Current metrics - ensure scalar values
            current_price = price_data["close"].iloc[-1]
            current_price = current_price.item() if hasattr(current_price, "item") else float(current_price)
            current_volume = price_data["volume"].iloc[-1]
            current_volume = current_volume.item() if hasattr(current_volume, "item") else float(current_volume)

            # Average volume (20-day)
            avg_volume = price_data["volume"].rolling(window=20).mean().iloc[-1]
            avg_volume = avg_volume.item() if hasattr(avg_volume, "item") else float(avg_volume)

            # Relative volume
            relative_volume = current_volume / avg_volume if avg_volume > 0 else 0.0

            # Momentum
            past_price = price_data["close"].iloc[-self.criteria.momentum_period]
            past_price = past_price.item() if hasattr(past_price, "item") else float(past_price)
            momentum_pct = ((current_price - past_price) / past_price * 100)

            # ATR
            atr = self._calculate_atr(price_data)
            atr_pct = (atr / current_price) * 100.0 if current_price > 0 else 0.0

            # Dollar volume
            dollar_volume = current_price * current_volume

            # Check criteria
            matched_criteria = []

            if current_price < self.criteria.min_price:
                return None
            if current_price > self.criteria.max_price:
                return None
            if avg_volume < self.criteria.min_volume:
                return None
            if dollar_volume < self.criteria.min_dollar_volume:
                return None

            # Positive criteria matching
            if momentum_pct >= self.criteria.min_momentum_pct:
                matched_criteria.append("high_momentum")

            if relative_volume >= self.criteria.min_relative_volume:
                matched_criteria.append("high_relative_volume")

            if self.criteria.min_atr_pct <= atr_pct <= self.criteria.max_atr_pct:
                matched_criteria.append("good_volatility")

            # Calculate composite score (0-100)
            score = self._calculate_score(
                momentum_pct=momentum_pct,
                relative_volume=relative_volume,
                atr_pct=atr_pct,
            )

            # Require at least one positive criterion
            if not matched_criteria:
                return None

            result = ScanResult(
                ticker=ticker,
                price=current_price,
                volume=int(current_volume),
                relative_volume=relative_volume,
                momentum_pct=momentum_pct,
                atr_pct=atr_pct,
                score=score,
                matched_criteria=matched_criteria,
                timestamp=datetime.now(),
            )

            self._scan_cache[ticker] = result
            return result

        except Exception as e:
            _LOG.warning("Error scanning %s: %s", ticker, e)
            return None

    def scan_universe(
        self,
        universe: list[str],
        data_fetcher: callable,
    ) -> list[ScanResult]:
        """
        Scan entire universe of stocks.

        Args:
            universe: List of ticker symbols to scan
            data_fetcher: Function that takes ticker and returns price DataFrame

        Returns:
            List of ScanResult objects, sorted by score
        """
        results = []

        _LOG.info("Scanning %d tickers...", len(universe))

        for ticker in universe:
            try:
                price_data = data_fetcher(ticker)
                if price_data is not None and len(price_data) > 0:
                    result = self.scan_ticker(ticker, price_data)
                    if result:
                        results.append(result)
                        _LOG.info(
                            "%s: Score=%.1f, Momentum=%.1f%%, RelVol=%.1fx (%s)",
                            ticker,
                            result.score,
                            result.momentum_pct,
                            result.relative_volume,
                            ", ".join(result.matched_criteria),
                        )
            except Exception as e:
                _LOG.warning("Error processing %s: %s", ticker, e)
                continue

        # Sort by score (highest first)
        results.sort(key=lambda x: x.score, reverse=True)

        _LOG.info("Scan complete: %d / %d tickers passed screening", len(results), len(universe))

        return results

    def get_top_opportunities(self, n: int = 10) -> list[ScanResult]:
        """
        Get top N opportunities from cached scan results.

        Args:
            n: Number of top opportunities to return

        Returns:
            List of top ScanResult objects
        """
        # Filter out stale results (> 1 hour old)
        cutoff_time = datetime.now() - timedelta(hours=1)
        fresh_results = [
            r
            for r in self._scan_cache.values()
            if r.timestamp > cutoff_time
        ]

        # Sort by score
        fresh_results.sort(key=lambda x: x.score, reverse=True)

        return fresh_results[:n]

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range."""
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift())
        low_close = abs(df["low"] - df["close"].shift())

        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)

        atr = true_range.rolling(window=period).mean().iloc[-1]

        # Ensure float return
        return float(atr) if not pd.isna(atr) else 0.0

    def _calculate_score(
        self,
        momentum_pct: float,
        relative_volume: float,
        atr_pct: float,
    ) -> float:
        """
        Calculate composite opportunity score (0-100).

        Weights:
        - Momentum: 40%
        - Relative Volume: 30%
        - Volatility: 30%
        """
        # Momentum score (0-40)
        momentum_score = min(40, (momentum_pct / 10) * 40)

        # Relative volume score (0-30)
        rel_vol_score = min(30, ((relative_volume - 1) / 2) * 30)

        # Volatility score (0-30) - prefer 2-3% ATR
        ideal_atr = 2.5
        volatility_score = 30 - (abs(atr_pct - ideal_atr) * 5)
        volatility_score = max(0, min(30, volatility_score))

        total_score = momentum_score + rel_vol_score + volatility_score

        return round(total_score, 1)
