from .base import Signal, Strategy, StrategyDiagnostics
from .trend_following import TrendFollowingStrategy
from .mean_reversion import MeanReversionStrategy
from .momentum_breakout import MomentumBreakoutStrategy

# Legacy imports (if old strategy files still exist)
try:
    from .dual_ma_mean_reversion import DualMAMeanReversionStrategy
    from .intraday_pair_spread import IntradayPairSpreadStrategy
    _legacy_available = True
except ImportError:
    _legacy_available = False


def create_strategy(config, data_service):
    """Create strategy instance from config."""
    name = config.strategy.name

    # New multi-strategy system
    if name == "trend_following":
        return TrendFollowingStrategy(config.strategy.params)
    if name == "mean_reversion":
        return MeanReversionStrategy(config.strategy.params)
    if name == "momentum_breakout":
        return MomentumBreakoutStrategy(config.strategy.params)

    # Legacy strategies (if available)
    if _legacy_available:
        if name == "dual_ma_mean_reversion":
            return DualMAMeanReversionStrategy(config, data_service)
        if name == "intraday_pair_spread":
            return IntradayPairSpreadStrategy(config, data_service)

    raise ValueError(f"Unsupported strategy '{name}'")


__all__ = [
    "Signal",
    "Strategy",
    "StrategyDiagnostics",
    "TrendFollowingStrategy",
    "MeanReversionStrategy",
    "MomentumBreakoutStrategy",
    "create_strategy",
]
