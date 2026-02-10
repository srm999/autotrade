"""Test the daily reporting functionality.

This script simulates a trading day with various activities
to demonstrate the daily summary report.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add autotrade to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from autotrade.trading.reporting import PerformanceReporter

print("=" * 80)
print("TESTING DAILY SUMMARY REPORT")
print("=" * 80)

# Create reporter
reporter = PerformanceReporter(reports_dir="reports")

print("\n1. Simulating market regime changes...")
reporter.record_regime_change(
    "BULL Strong Trend (Medium Vol)",
    ["Trend Following", "Momentum Breakout"]
)
print("   ✓ Recorded regime: BULL Strong Trend")

# Simulate some time passing
import time
time.sleep(1)

print("\n2. Simulating trading signals...")
# Entry signal - executed
reporter.record_signal(
    ticker="AAPL",
    signal_type="entry",
    strategy="Momentum Breakout",
    confidence=0.85,
    executed=True,
)
print("   ✓ AAPL entry signal (executed)")

# Entry signal - ignored (low confidence)
reporter.record_signal(
    ticker="MSFT",
    signal_type="entry",
    strategy="Mean Reversion",
    confidence=0.45,
    executed=False,
)
print("   ✓ MSFT entry signal (ignored)")

print("\n3. Simulating trades...")
# Entry trade
reporter.record_trade(
    ticker="AAPL",
    action="buy",
    quantity=50,
    price=175.25,
    strategy="Momentum Breakout",
    pnl=None,  # No P&L for entry
)
print("   ✓ BUY 50 AAPL @ $175.25")

time.sleep(1)

# Exit signal
reporter.record_signal(
    ticker="AAPL",
    signal_type="exit",
    strategy="Momentum Breakout",
    confidence=0.75,
    executed=True,
)
print("   ✓ AAPL exit signal (executed)")

# Exit trade with profit
exit_price = 182.50
entry_price = 175.25
pnl = (exit_price - entry_price) * 50

reporter.record_trade(
    ticker="AAPL",
    action="sell",
    quantity=50,
    price=exit_price,
    strategy="Momentum Breakout",
    pnl=pnl,
)
print(f"   ✓ SELL 50 AAPL @ ${exit_price} (P&L: +${pnl:.2f})")

# Another entry
reporter.record_trade(
    ticker="NVDA",
    action="buy",
    quantity=25,
    price=485.00,
    strategy="Trend Following",
    pnl=None,
)
print("   ✓ BUY 25 NVDA @ $485.00")

print("\n4. Simulating regime change (mid-day)...")
time.sleep(1)
reporter.record_regime_change(
    "BULL Weak Trend (Low Vol)",
    ["Trend Following"]
)
print("   ✓ Regime changed to: BULL Weak Trend")

print("\n5. Simulating an error...")
try:
    raise ValueError("Insufficient funds for trade")
except ValueError as e:
    reporter.record_error(e, context="execute_trade")
    print(f"   ✓ Recorded error: {e}")

print("\n6. Generating daily summary report...")
report = reporter.generate_daily_summary()

print("\n" + "=" * 80)
print("DAILY SUMMARY REPORT GENERATED")
print("=" * 80)
print(report)

print("\n" + "=" * 80)
print(f"Report saved to: reports/daily_summary_{datetime.now().date().isoformat()}.txt")
print("=" * 80)

# Show performance summary
print("\nPerformance Summary:")
summary = reporter.get_summary()
print(f"  Total trades: {summary['total_trades']}")
print(f"  Completed trades: {summary['completed_trades']}")
print(f"  Win rate: {summary['win_rate']:.1f}%")
print(f"  Total P&L: +${summary['total_pnl']:.2f}")
print(f"  Avg P&L per trade: +${summary['avg_pnl']:.2f}")

print("\n✅ Test complete!")
