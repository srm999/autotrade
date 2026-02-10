"""Quick test script for multi-strategy system.

Tests:
1. Market regime detection
2. Strategy compatibility
3. Stock screener
4. Watchlist manager
5. Strategy manager

Run this to verify all components work correctly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Add autotrade to path
sys.path.insert(0, str(Path(__file__).parent.parent))

print("=" * 80)
print("MULTI-STRATEGY SYSTEM TEST")
print("=" * 80)

# Test 1: Market Regime Detection
print("\n[TEST 1] Market Regime Detection")
print("-" * 80)

try:
    import yfinance as yf
    from autotrade.analysis.market_regime import MarketRegimeDetector

    print("Fetching SPY data...")
    spy_data = yf.download("SPY", period="1y", progress=False)

    # Extract close prices as a proper Series
    if isinstance(spy_data["Close"], pd.DataFrame):
        close_prices = spy_data["Close"].squeeze()
    else:
        close_prices = spy_data["Close"]

    print("Detecting market regime...")
    detector = MarketRegimeDetector()
    regime = detector.detect_regime(close_prices)

    print(f"\n✅ Market Regime: {regime}")
    print(f"   - Trend Direction: {regime.trend_direction.value.upper()}")
    print(f"   - Trend Strength: {regime.trend_strength.value.replace('_', ' ').title()}")
    print(f"   - Volatility: {regime.volatility.value.title()}")
    print(f"   - ADX: {regime.adx:.1f} (>25 = strong trend, <20 = ranging)")
    print(f"   - SMA-50: ${regime.sma_50:.2f}")
    print(f"   - SMA-200: ${regime.sma_200:.2f}")

except Exception as e:
    print(f"❌ ERROR: {e}")
    sys.exit(1)

# Test 2: Strategy Compatibility
print("\n[TEST 2] Strategy Compatibility")
print("-" * 80)

try:
    from autotrade.config import (
        MeanReversionParams,
        MomentumBreakoutParams,
    )
    from autotrade.strategy.mean_reversion import MeanReversionStrategy
    from autotrade.strategy.momentum_breakout import MomentumBreakoutStrategy

    strategies = [
        ("Mean Reversion", MeanReversionStrategy(MeanReversionParams())),
        ("Momentum Breakout", MomentumBreakoutStrategy(MomentumBreakoutParams())),
    ]

    print(f"Testing strategies against current regime: {regime}\n")

    for name, strategy in strategies:
        compatible = strategy.is_compatible_with_regime(regime)
        status = "✅ ACTIVE" if compatible else "❌ INACTIVE"
        print(f"   {name}: {status}")

except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Test 3: Stock Screener
print("\n[TEST 3] Stock Screener")
print("-" * 80)

try:
    from autotrade.scanner.stock_screener import StockScreener

    screener = StockScreener()
    test_universe = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]

    print(f"Scanning {len(test_universe)} tickers: {', '.join(test_universe)}")

    def fetch_data(ticker):
        try:
            data = yf.download(ticker, period="50d", progress=False)
            if len(data) == 0:
                return None
            # Rename columns to expected format
            data = data.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
            return data
        except Exception:
            return None

    results = screener.scan_universe(test_universe, fetch_data)

    if results:
        print(f"\n✅ Found {len(results)} opportunities:\n")
        for result in results[:5]:  # Top 5
            print(f"   {result.ticker}:")
            print(f"      Score: {result.score:.1f}/100")
            print(f"      Momentum: {result.momentum_pct:+.1f}%")
            print(f"      Relative Volume: {result.relative_volume:.2f}x")
            print(f"      Criteria: {', '.join(result.matched_criteria)}")
            print()
    else:
        print("⚠️  No opportunities found (normal in quiet markets)")

except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Test 4: Watchlist Manager
print("\n[TEST 4] Watchlist Manager")
print("-" * 80)

try:
    from autotrade.scanner.watchlist import WatchlistManager

    watchlist_mgr = WatchlistManager()

    # Create test watchlist
    test_watchlist = watchlist_mgr.create_watchlist(
        name="test_watchlist",
        tickers=["SPY", "QQQ", "IWM"],
        description="Test watchlist",
    )

    print(f"✅ Created test watchlist with {len(test_watchlist.tickers)} tickers")

    # Add ticker
    test_watchlist.add_ticker("AAPL")
    print(f"✅ Added AAPL to watchlist")

    # Get combined tickers
    all_tickers = watchlist_mgr.get_combined_tickers()
    print(f"✅ Total unique tickers across all watchlists: {len(all_tickers)}")

    # Clean up
    watchlist_mgr.delete_watchlist("test_watchlist")
    print(f"✅ Cleaned up test watchlist")

except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Test 5: Strategy Manager
print("\n[TEST 5] Strategy Manager")
print("-" * 80)

try:
    from autotrade.strategy.strategy_manager import StrategyManager

    strategy_mgr = StrategyManager()

    # Register all strategies
    for name, strategy in strategies:
        strategy_mgr.register_strategy(strategy, auto_activate=False)

    print(f"✅ Registered {len(strategies)} strategies")

    # Update regime
    strategy_mgr.update_regime(regime)

    # Get active strategies
    active = strategy_mgr.get_active_strategies()
    print(f"✅ Active strategies for current regime: {', '.join(active) if active else 'None (cash preservation)'}")

    # Get status
    status = strategy_mgr.get_strategy_status()
    print(f"✅ Strategy status retrieved: {len(status)} strategies tracked")

except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Summary
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print("\n✅ All components working correctly!")
print("\nNext steps:")
print("   1. Run backtests: python3 scripts/backtest_runner.py")
print("   2. Test bot in dry-run: python3 main_multi_strategy.py --dry-run")
print("   3. Read documentation: docs/MULTI_STRATEGY_GUIDE.md")
print("\n" + "=" * 80)
