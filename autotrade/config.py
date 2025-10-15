"""Centralized configuration for the trading bot."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class RobinhoodCredentials:
    username: str
    password: str
    mfa_code: str | None = None
    device_token: str | None = None

    @classmethod
    def from_env(cls) -> "RobinhoodCredentials":
        username = os.getenv("ROBINHOOD_USERNAME")
        password = os.getenv("ROBINHOOD_PASSWORD")
        if not username or not password:
            raise ValueError("Missing Robinhood credentials. Set ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD.")
        return cls(
            username=username,
            password=password,
            mfa_code=os.getenv("ROBINHOOD_MFA_CODE"),
            device_token=os.getenv("ROBINHOOD_DEVICE_TOKEN"),
        )


@dataclass(frozen=True)
class TradingWindow:
    market_open: time
    market_close: time


@dataclass(frozen=True)
class DualMAMeanReversionParams:
    fast_window: int = 50
    slow_window: int = 250
    std_lookback: int = 20
    entry_zscore: float = 1.0
    exit_zscore: float = 0.0
    stop_loss_pct: float = 0.03
    regime_confirm_days: int = 3
    flatten_minutes_before_close: int = 10


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    tickers: tuple[str, ...]
    max_position_size: float
    max_total_exposure: float
    params: DualMAMeanReversionParams


@dataclass(frozen=True)
class BotConfig:
    strategy: StrategyConfig
    trading_window: TradingWindow
    polling_interval_seconds: int

    @classmethod
    def default(cls) -> "BotConfig":
        strategy = StrategyConfig(
            name="dual_ma_mean_reversion",
            tickers=("TQQQ", "SQQQ"),
            max_position_size=10_000.0,
            max_total_exposure=15_000.0,
            params=DualMAMeanReversionParams(),
        )
        window = TradingWindow(market_open=time(9, 30), market_close=time(16, 0))
        return cls(strategy=strategy, trading_window=window, polling_interval_seconds=60)
