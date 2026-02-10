## 🚀 Quick Start: Strategic Pivot to Daily/Swing Trading

**Goal**: Build a sustainable trading system with $10k capital focusing on longer timeframes and non-leveraged instruments.

---

## What Changed?

| Old Approach | New Approach |
|--------------|--------------|
| Intraday (1-minute bars) | Daily/EOD (end-of-day signals) |
| TQQQ/SQQQ (3x leveraged) | SPY/QQQ/Large Caps (non-leveraged) |
| $1,500 capital | $10,000 capital |
| 33% daily loss tolerance | 2% daily loss tolerance |
| Fixed position sizing | Volatility-adjusted sizing (ATR-based) |

---

## Phase 1: Backtesting (CURRENT PHASE)

**You are here! Do NOT skip to live trading.**

### Step 1: Install Dependencies

```bash
# Add yfinance for historical data
pip install yfinance

# Update requirements.txt
echo "yfinance>=0.2.30" >> requirements.txt
pip install -r requirements.txt
```

### Step 2: Implement Data Loading

Edit [`scripts/backtest_runner.py`](../scripts/backtest_runner.py) and implement the `load_historical_data()` function:

```python
import yfinance as yf

def load_historical_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Load historical data using yfinance."""
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)

    # Rename columns to match expected format
    data = data.rename(columns={
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close',
        'Volume': 'volume'
    })

    data['date'] = data.index
    return data.reset_index(drop=True)
```

### Step 3: Run Your First Backtest

```bash
# Test trend following strategy on SPY (2020-2024)
python scripts/backtest_runner.py \
    --strategy trend_following \
    --start 2020-01-01 \
    --end 2024-12-31 \
    --capital 10000 \
    --log-level INFO
```

### Step 4: Analyze Results

Look for:
- **Sharpe Ratio > 1.0** (good risk-adjusted returns)
- **Max Drawdown < 25%** (manageable losses)
- **Win Rate > 40%** (reasonable hit rate)
- **Profit Factor > 2.0** (winners 2x bigger than losers)

### Step 5: Test Multiple Market Conditions

```bash
# Bull market (2020-2021)
python scripts/backtest_runner.py --start 2020-01-01 --end 2021-12-31

# Bear market (2022)
python scripts/backtest_runner.py --start 2022-01-01 --end 2022-12-31

# Recovery (2023-2024)
python scripts/backtest_runner.py --start 2023-01-01 --end 2024-12-31
```

**Strategy must work in ALL market conditions, not just bull markets!**

---

## Phase 2: Strategy Refinement (2-4 Weeks)

### Optimize Parameters (Carefully!)

```python
# In autotrade/strategy/trend_following.py
# Test different parameters:

# More aggressive (shorter timeframes)
TrendFollowingParams(
    sma_fast=20,  # vs 50
    sma_slow=100,  # vs 200
    atr_stop_multiplier=1.5  # vs 2.0
)

# More conservative (longer timeframes)
TrendFollowingParams(
    sma_fast=100,
    sma_slow=300,
    atr_stop_multiplier=3.0
)
```

**⚠️ Warning**: Avoid over-optimization (curve-fitting)!
- Test on out-of-sample data (2025+)
- Use walk-forward analysis
- If Sharpe > 2.5 in backtest, probably overfitted

### Add More Tickers

```python
# In config.py, update tickers:
tickers=("SPY", "QQQ", "IWM", "DIA")  # Add more for diversification
```

### Calculate Transaction Costs

```python
# Expected costs per trade:
# - Slippage: 0.05% (5 basis points)
# - SEC fees: ~$0.028 per $1000 sold
# - TAF fees: negligible
# Total: ~$2-5 per $1000 trade

# On $2,500 position: $6.25 cost per round trip
# Need > $6.25 profit to break even
# Need > $25 profit to be worthwhile (4:1 ratio)
```

---

## Phase 3: Paper Trading (6+ Months)

**Do NOT skip this phase!**

### Why Paper Trade?

Backtesting can't simulate:
- Real-time data feed issues
- API connectivity problems
- Your emotional responses
- Slippage variability
- News events and gaps

### Run Paper Trading

```bash
# Paper trading with trend following
python main.py \
    --strategy trend_following \
    --dry-run \
    --log-level INFO
```

### Monitor These Metrics

Create a spreadsheet tracking:
- Date
- Ticker
- Entry Price
- Exit Price
- Hold Days
- P&L ($)
- P&L (%)
- Cumulative P&L
- Drawdown from Peak

### Success Criteria for Paper Trading

After 6 months, check:
- [ ] Sharpe ratio matches backtest within 20%
- [ ] Max drawdown not significantly worse than backtest
- [ ] Win rate within 5% of backtest
- [ ] No major system failures or crashes
- [ ] Emotional control maintained (not checking every hour)

### Common Paper Trading Discoveries

Things you'll learn:
1. **Slippage is worse than expected** (especially on thinly traded stocks)
2. **Data feed delays cause missed trades** (price moved before your order)
3. **Emotional difficulty with losses** (even fake money hurts!)
4. **Bugs you didn't catch in backtest** (data edge cases, timezone issues)

---

## Phase 4: Micro-Live (Month 9+)

### Start VERY Small

```bash
# Use only $1,000 (10% of capital)
python main.py \
    --strategy trend_following \
    --capital 1000  # Override config
    # NO --dry-run flag (this is real!)
```

### Run Alongside Paper Trading

- Keep paper trading running with full $10k
- Compare results every week
- If micro-live significantly underperforms paper → STOP, investigate

### Monitor Execution Quality

Track:
- **Fill price vs expected price** (slippage)
- **Time from signal to fill** (latency)
- **Partial fills** (order didn't fully execute)
- **Rejected orders** (insufficient capital, etc.)

### Scale Up Gradually

Only increase capital if:
- 3+ months of micro-live successful
- Results match paper trading
- No emotional issues
- System runs reliably

Scale up schedule:
- Month 1-3: $1,000
- Month 4-6: $2,500
- Month 7-9: $5,000
- Month 10+: $10,000 (full capital)

---

## Key Metrics to Track

### Performance Metrics

| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| Sharpe Ratio | > 1.5 | 1.0 - 1.5 | < 1.0 |
| Max Drawdown | < 15% | 15% - 25% | > 25% |
| Win Rate | > 50% | 40% - 50% | < 40% |
| Profit Factor | > 2.5 | 2.0 - 2.5 | < 2.0 |
| Monthly Return | > 1.5% | 0.8% - 1.5% | < 0.8% |

### Portfolio Metrics

Track daily:
```
Cash: $X,XXX
Positions: X open (list tickers)
Exposure: XX% (positions value / total capital)
P&L Today: $XX
P&L This Week: $XX
P&L This Month: $XX
Drawdown from Peak: X.X%
```

---

## Tools & Resources

### Recommended Additions

```bash
# Visualization
pip install matplotlib seaborn plotly

# Statistical analysis
pip install scipy statsmodels

# Notebook for analysis
pip install jupyter notebook
```

### Helpful Libraries

```python
# Equity curve visualization
import matplotlib.pyplot as plt

def plot_equity_curve(results):
    """Plot backtest equity curve."""
    plt.figure(figsize=(12, 6))
    results.equity_curve.plot()
    plt.title('Equity Curve')
    plt.xlabel('Date')
    plt.ylabel('Portfolio Value ($)')
    plt.grid(True)
    plt.show()

# Drawdown visualization
def plot_drawdown(results):
    """Plot drawdown over time."""
    equity = results.equity_curve
    running_max = equity.expanding().max()
    drawdown = (equity - running_max) / running_max * 100

    plt.figure(figsize=(12, 4))
    drawdown.plot(color='red', alpha=0.7)
    plt.title('Drawdown Over Time')
    plt.xlabel('Date')
    plt.ylabel('Drawdown (%)')
    plt.grid(True)
    plt.show()
```

---

## Common Mistakes to Avoid

### ❌ DON'T:
1. Skip backtesting ("I'll learn as I go")
2. Over-optimize parameters to maximize backtest returns
3. Test only on bull markets
4. Ignore transaction costs
5. Skip paper trading phase
6. Start with full capital
7. Check portfolio every hour (leads to emotional decisions)
8. Add new strategies without testing
9. Revenge trade after losses
10. Expect "regular income" (trading is volatile!)

### ✅ DO:
1. Backtest extensively (5+ years, multiple market conditions)
2. Use realistic cost assumptions (0.10-0.15% per trade)
3. Paper trade for 6+ months minimum
4. Start micro-live with 10% of capital
5. Track every metric religiously
6. Accept losses as part of the process
7. Follow your system rules mechanically
8. Be patient (3-5 years to profitability)
9. Keep learning and iterating
10. Have a stop condition (if Sharpe < 0.5 after 12 months, pivot)

---

## Expected Timeline

### Realistic Path to Success

```
Month 1-2:   Build backtesting framework ✓ (DONE!)
Month 3-4:   Backtest and refine strategies
Month 5-6:   Walk-forward testing and optimization
Month 7-12:  Paper trading (6 months minimum)
Month 13-15: Micro-live trading ($1k)
Month 16-18: Scale to $2.5k
Month 19-21: Scale to $5k
Month 22+:   Full capital ($10k) if successful
```

**Total time to full deployment: ~2 years**

This seems long, but it's realistic. Most profitable algo traders spent 3-5 years before consistent success.

---

## When to Stop/Pivot

### Red Flags (Time to Reconsider)

After 12 months, if you have:
- Sharpe ratio < 0.3 consistently
- Drawdown > 40%
- Negative returns despite refinements
- Lost discipline (not following rules)
- Too much emotional stress

**Consider**: Maybe algo trading isn't right for you (and that's okay!).

### Alternative Paths

If algo trading doesn't work:
1. **Buy and hold index funds** (SPY, QQQ) - 10% annual returns, zero work
2. **Covered calls** - Income on stocks you own
3. **Dividend investing** - Actual "regular income"
4. **Focus on career** - $10k invested in skills → much higher ROI

---

## Next Steps

1. ✅ Read [STRATEGIC_PIVOT.md](./STRATEGIC_PIVOT.md) for full context
2. ✅ Review [CRITICAL_FIXES_REFERENCE.md](./CRITICAL_FIXES_REFERENCE.md) for system details
3. ⏳ Implement `load_historical_data()` in backtest runner
4. ⏳ Run first backtest on SPY (2020-2024)
5. ⏳ Analyze results and iterate

---

**Remember**: The goal is not to get rich quick. The goal is to build a systematic, evidence-based approach that has a chance of working over years.

Good luck! 🚀
