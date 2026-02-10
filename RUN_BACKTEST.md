# Run Your First Backtest - Quick Guide

## Step 1: Install Dependencies (2 minutes)

```bash
# Make sure you're in the autotrade directory
cd /Users/sunil/Source/autotrade

# Install new dependencies
pip install -r requirements.txt
```

This installs `yfinance` and `numpy` which are needed for historical data.

---

## Step 2: Run the Backtest (1 minute)

```bash
# Basic backtest: SPY, QQQ, IWM from 2020-2024
python scripts/backtest_runner.py
```

This will:
1. Download historical data from Yahoo Finance
2. Calculate indicators (moving averages, ATR)
3. Run the trend following strategy
4. Show complete performance metrics

**Expected runtime**: 30-60 seconds

---

## Step 3: Interpret Results

The script will show:

### Performance Metrics
```
Performance Metrics
===================
Returns:
  Total Return:           XX.XX%
  Annual Return (CAGR):   XX.XX%
  Monthly Return:         XX.XX%

Risk-Adjusted:
  Sharpe Ratio:           X.XX    <-- GOAL: > 1.0
  Sortino Ratio:          X.XX
  Calmar Ratio:           X.XX

Risk:
  Max Drawdown:           XX.XX%  <-- GOAL: < 25%

Trade Statistics:
  Win Rate:               XX.X%   <-- GOAL: > 40%
  Profit Factor:          X.XX    <-- GOAL: > 2.0
```

### Quality Check
```
QUALITY CHECK
================================================================================
  Sharpe Ratio > 1.0: ✅ PASS (1.23)
  Max Drawdown < 25%: ✅ PASS (18.50%)
  Win Rate > 40%: ✅ PASS (45.2%)
  Profit Factor > 2.0: ✅ PASS (2.15)

================================================================================
✅ STRATEGY MEETS MINIMUM STANDARDS
Next step: Test on different time periods and market conditions
================================================================================
```

---

## Step 4: Test Different Scenarios

### Test Bear Market (2022)
```bash
python scripts/backtest_runner.py --start 2022-01-01 --end 2022-12-31
```

**Important**: Strategy should survive bear markets without catastrophic losses.

### Test Bull Market (2023)
```bash
python scripts/backtest_runner.py --start 2023-01-01 --end 2023-12-31
```

### See All Trades
```bash
python scripts/backtest_runner.py --show-trades
```

This shows every buy/sell with entry/exit prices and P&L.

### Test with Different Capital
```bash
python scripts/backtest_runner.py --capital 50000
```

Position sizes will scale proportionally.

---

## Step 5: What to Look For

### ✅ Good Signs
- Sharpe ratio > 1.0 (ideally > 1.2)
- Max drawdown < 20% (shows good risk control)
- Win rate 40-50% (trend following typically has lower win rate but big winners)
- Profit factor > 2.0 (winners are 2x bigger than losers)
- Consistent across different time periods

### ⚠️ Warning Signs
- Sharpe ratio < 0.8
- Max drawdown > 30%
- Win rate < 35%
- Profit factor < 1.5
- Works in bull markets but fails in bear markets
- Very few trades (< 20 total over 5 years)

### ❌ Red Flags
- Sharpe ratio < 0.5
- Max drawdown > 40%
- Negative returns
- Only works in one specific market condition

---

## Common Issues & Solutions

### Issue: "yfinance not installed"
```bash
pip install yfinance
```

### Issue: "No data loaded for any tickers"
- Check your internet connection
- Yahoo Finance might be down (rare)
- Try again in a few minutes

### Issue: Very few or no trades
- This is expected! Trend following waits for strong signals
- Try longer time period: `--start 2018-01-01 --end 2024-12-31`
- Or try more aggressive parameters (edit config.py)

### Issue: Poor results (Sharpe < 0.5)
This is actually normal! Many strategies fail backtesting. Options:
1. **Adjust parameters** (in `autotrade/config.py` - TrendFollowingParams)
2. **Try different tickers** (add more or change selection)
3. **Accept it doesn't work** and try a different strategy

---

## Next Steps After Successful Backtest

If you get **Sharpe > 1.0** and **all quality checks pass**:

1. ✅ **Test on 2018-2019 data** (out-of-sample)
   ```bash
   python scripts/backtest_runner.py --start 2018-01-01 --end 2019-12-31
   ```

2. ✅ **Test on 2015-2017 data** (even more out-of-sample)
   ```bash
   python scripts/backtest_runner.py --start 2015-01-01 --end 2017-12-31
   ```

3. ✅ **Test different parameter combinations**
   - Edit `autotrade/config.py` → `TrendFollowingParams`
   - Try `sma_fast=20` vs `sma_fast=100`
   - Try `atr_stop_multiplier=1.5` vs `3.0`

4. ✅ **Start paper trading**
   - Run for 6 months minimum
   - Track vs backtest expectations

5. ⏳ **After 6+ months paper trading → Micro-live**
   - Start with $1,000 (10% of capital)
   - Compare to paper trading results

---

## Full Command Reference

```bash
# Default: 2020-2024, $10k capital
python scripts/backtest_runner.py

# Custom date range
python scripts/backtest_runner.py --start 2018-01-01 --end 2023-12-31

# Custom capital
python scripts/backtest_runner.py --capital 50000

# Show all trades
python scripts/backtest_runner.py --show-trades

# More detailed logging
python scripts/backtest_runner.py --log-level DEBUG

# Combine options
python scripts/backtest_runner.py \
    --start 2020-01-01 \
    --end 2024-12-31 \
    --capital 25000 \
    --show-trades \
    --log-level INFO
```

---

## Understanding the Strategy

The backtest implements **Trend Following**:

**Entry Signals** (all must be true):
1. Price > 50-day MA (short-term uptrend)
2. 50-day MA > 200-day MA (long-term uptrend)
3. Price breaks above 20-day high (momentum confirmation)

**Exit Signals** (any triggers exit):
1. Price < 10-day MA (trend reversal)
2. Price < Entry - (2 × ATR) (stop loss hit)
3. Held for 30+ days (time stop)

**Position Sizing**:
- Risk 2% of capital per trade
- Size based on ATR (volatility-adjusted)
- Max 5 positions simultaneously
- Max 25% per position

---

## What Success Looks Like

### Realistic Results on $10k (2020-2024)
- **Total Return**: +40% to +80% (over 5 years)
- **Annual Return**: 7% to 12%
- **Sharpe Ratio**: 0.8 to 1.3
- **Max Drawdown**: 15% to 25%
- **Total Trades**: 30-60 trades
- **Win Rate**: 40-48%
- **Avg Hold Time**: 10-20 days

### What This Means in Dollars
- Starting: $10,000
- Ending: $14,000 - $18,000 (over 5 years)
- **That's $800-1,600 per year**
- **Or $65-135 per month average** (highly variable!)

**Remember**: This is NOT "regular income" - some months will be -$200, others +$400.

---

## Ready? Run Your First Backtest!

```bash
python scripts/backtest_runner.py
```

Then check the results and see if your strategy meets minimum standards! 🚀
