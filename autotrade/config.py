"""Centralized configuration for the trading bot."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from typing import Any


@dataclass(frozen=True)
class SchwabCredentials:
    app_key: str
    app_secret: str
    account_number: str
    token_path: str
    account_hash: str | None = None

    @classmethod
    def from_env(cls) -> "SchwabCredentials":
        app_key = (os.getenv("SCHWAB_APP_KEY") or "").strip()
        app_secret = (os.getenv("SCHWAB_APP_SECRET") or "").strip()
        account_number = (os.getenv("SCHWAB_ACCOUNT_NUMBER") or "").strip()
        token_path = (os.getenv("SCHWAB_TOKEN_PATH") or "data/schwab_token.json").strip()
        account_hash = (os.getenv("SCHWAB_ACCOUNT_HASH") or "").strip() or None
        if not app_key or not app_secret:
            raise ValueError("Missing Schwab API credentials. Set SCHWAB_APP_KEY and SCHWAB_APP_SECRET.")
        if not account_number:
            raise ValueError("Missing Schwab account hash. Set SCHWAB_ACCOUNT_NUMBER.")
        return cls(
            app_key=app_key,
            app_secret=app_secret,
            account_number=account_number,
            token_path=token_path,
            account_hash=account_hash,
        )


@dataclass(frozen=True)
class TradingWindow:
    market_open: time
    market_close: time


@dataclass(frozen=True)
class IntradayPairSpreadParams:
    lookback_bars: int = 20  # Shorter window = faster adaptation (was 60)
    entry_zscore: float = 1.8  # More aggressive entries (was 2.0)
    exit_zscore: float = 0.4  # Tighter exits (was 0.5)
    max_hold_minutes: int = 45  # Shorter holds reduce risk (was 60)
    cooldown_minutes: int = 10  # Wait between trades
    interval: str = "1minute"  # 1-minute bars
    flatten_minutes_before_close: int = 5  # Close positions early


@dataclass(frozen=True)
class BollingerBreakoutParams:
    """Bollinger Band breakout strategy parameters."""
    lookback_period: int = 20  # Period for SMA and std dev calculation
    std_multiplier: float = 2.0  # Standard deviation multiplier for bands
    max_hold_minutes: int = 240  # Max hold time (4 hours)
    flatten_minutes_before_close: int = 10  # Close positions 10 min early


@dataclass(frozen=True)
class MomentumParams:
    """Simple momentum strategy parameters."""
    lookback_days: int = 20  # Period to identify highs/lows
    breakout_pct: float = 0.02  # Require 2% breakout above high
    stop_loss_pct: float = 0.03  # 3% stop loss
    max_hold_days: int = 5  # Max hold time in days
    flatten_minutes_before_close: int = 10  # Close positions early


@dataclass(frozen=True)
class TrendFollowingParams:
    """Trend following strategy parameters (daily/swing timeframe)."""
    sma_fast: int = 50  # Fast trend MA
    sma_slow: int = 200  # Slow trend MA
    sma_exit: int = 10  # Exit MA (faster)
    breakout_period: int = 20  # Breakout lookback period
    atr_period: int = 14  # ATR calculation period
    atr_stop_multiplier: float = 2.0  # Stop loss = entry - (ATR × multiplier)
    max_hold_days: int = 30  # Maximum hold period
    min_volume: int = 1_000_000  # Minimum daily volume


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


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Risk management circuit breaker settings."""
    max_daily_loss: float = 200.0  # Maximum daily loss in dollars (2% of $10k)
    max_consecutive_losses: int = 3  # Stop after N consecutive losing trades
    max_trades_per_hour: int = 5  # Maximum trade frequency
    enabled: bool = True  # Enable/disable circuit breakers


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    tickers: tuple[str, ...]
    max_position_size: float
    max_total_exposure: float
    params: Any


@dataclass(frozen=True)
class BotConfig:
    strategy: StrategyConfig
    trading_window: TradingWindow
    polling_interval_seconds: int
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()

    @classmethod
    def default(cls, *, strategy: str = "trend_following", capital: float = 10_000.0) -> "BotConfig":
        """
        Create default configuration for a strategy.

        Args:
            strategy: Strategy name
            capital: Total trading capital (default $10,000)

        Returns:
            BotConfig instance
        """
        strategy = strategy.lower()

        # NEW: Trend Following (daily/swing timeframe) - RECOMMENDED
        if strategy == "trend_following":
            strategy_config = StrategyConfig(
                name="trend_following",
                tickers=("SPY", "QQQ", "IWM"),  # Non-leveraged ETFs
                max_position_size=capital * 0.25,  # 25% per position (diversification)
                max_total_exposure=capital * 0.80,  # 80% max exposure (keep 20% cash)
                params=TrendFollowingParams(),
            )
            window = TradingWindow(market_open=time(9, 30), market_close=time(16, 0))
            circuit_breaker = CircuitBreakerConfig(
                max_daily_loss=capital * 0.02,  # 2% daily loss limit
                max_consecutive_losses=3,
                max_trades_per_hour=5,
                enabled=True
            )
            return cls(
                strategy=strategy_config,
                trading_window=window,
                polling_interval_seconds=300,  # Check every 5 minutes (less urgent for daily strategy)
                circuit_breaker=circuit_breaker
            )

        # OLD: Intraday strategies (NOT RECOMMENDED - high risk)
        if strategy == "intraday_pair_spread":
            strategy_config = StrategyConfig(
                name="intraday_pair_spread",
                tickers=("TQQQ", "SQQQ"),
                max_position_size=capital * 0.10,  # 10% per position
                max_total_exposure=capital * 0.15,  # 15% max exposure
                params=IntradayPairSpreadParams(),
            )
            window = TradingWindow(market_open=time(9, 30), market_close=time(16, 15))
            return cls(strategy=strategy_config, trading_window=window, polling_interval_seconds=60)

        if strategy == "bollinger_breakout":
            strategy_config = StrategyConfig(
                name="bollinger_breakout",
                tickers=("TQQQ", "SQQQ"),
                max_position_size=capital * 0.10,
                max_total_exposure=capital * 0.15,
                params=BollingerBreakoutParams(),
            )
            window = TradingWindow(market_open=time(9, 30), market_close=time(16, 00))
            return cls(strategy=strategy_config, trading_window=window, polling_interval_seconds=60)

        if strategy == "momentum":
            strategy_config = StrategyConfig(
                name="momentum",
                tickers=("TQQQ", "SQQQ"),
                max_position_size=capital * 0.10,
                max_total_exposure=capital * 0.15,
                params=MomentumParams(),
            )
            window = TradingWindow(market_open=time(9, 30), market_close=time(16, 00))
            return cls(strategy=strategy_config, trading_window=window, polling_interval_seconds=60)

        raise ValueError(f"Unsupported strategy '{strategy}'")
