## Multi-Strategy Trading Bot Guide

Your trading bot now supports **multiple strategies that automatically activate based on market conditions**. This guide explains how the system works and how to use it.

---

## 🎯 Overview

The multi-strategy bot:

1. **Runs continuously** during market hours (9:30 AM - 4:00 PM ET)
2. **Detects market regime** every hour (trending, ranging, volatile)
3. **Activates compatible strategies** automatically
4. **Scans watchlists** for trading setups
5. **Executes trades** when strong signals appear
6. **Manages risk** across all positions

---

## 📊 Available Strategies

### 1. Trend Following (Default)
**Best for:** Strong uptrends, medium-low volatility
**Entry:** Price breaks above 20-day high + MA crossover
**Exit:** Price crosses below 50 MA or ATR stop loss
**Hold time:** Up to 30 days

**When active:**
- Bull market with strong trend (ADX > 25)
- 50 MA > 200 MA (golden cross)

---

### 2. Mean Reversion
**Best for:** Ranging/choppy markets, neutral conditions
**Entry:** Price touches Bollinger Band + RSI oversold/overbought
**Exit:** Return to mean (20 SMA) or profit target (+2%)
**Hold time:** Typically 3-7 days

**When active:**
- ADX < 20 (weak trend / ranging market)
- Neutral market direction

**Technical signals:**
- LONG: Price ≤ Lower Bollinger Band + RSI < 30
- SHORT: Price ≥ Upper Bollinger Band + RSI > 70

---

### 3. Momentum Breakout
**Best for:** High volatility, explosive moves, strong trends
**Entry:** Price breaks 20-day high + volume > 1.5x average + strong momentum
**Exit:** Trend reversal, volume dries up, or max 10 days
**Hold time:** 3-10 days (momentum fades quickly)

**When active:**
- Strong trending market (ADX > 25)
- High volatility (VIX > 25 or ATR% > 2.5%)

**Technical signals:**
- +5% momentum over 20 days
- Volume confirmation (1.5x+ average)
- Breakout to new 20-day high

---

## 🔄 Market Regime Detection

The bot analyzes SPY (S&P 500) every hour to determine market conditions:

### Trend Direction
- **Bull:** Price > 50 MA > 200 MA
- **Bear:** Price < 50 MA < 200 MA
- **Neutral:** Mixed signals

### Trend Strength (ADX)
- **Strong Trend:** ADX > 25
- **Weak Trend:** ADX 20-25
- **Ranging:** ADX < 20

### Volatility
- **High:** VIX > 25 or ATR% > 2.5%
- **Medium:** VIX 15-25 or ATR% 1.5-2.5%
- **Low:** VIX < 15 or ATR% < 1.5%

---

## 🎯 Strategy Activation Matrix

| Market Condition | Active Strategies |
|-----------------|-------------------|
| Bull + Strong Trend + Medium Vol | **Trend Following**, Momentum Breakout |
| Bull + Weak Trend + Low Vol | **Trend Following** |
| Neutral + Ranging + Low Vol | **Mean Reversion** |
| Bull + Strong Trend + High Vol | **Momentum Breakout**, Trend Following |
| Bear + Strong Trend | **None** (stay in cash) |
| Neutral + Weak Trend | **Mean Reversion**, Trend Following |

**Bold** = Primary strategy for that regime

---

## 📋 Watchlists

The bot maintains multiple watchlists:

### 1. Primary Watchlist (Static)
User-defined tickers to always monitor.

**Default:** SPY, QQQ, IWM, AAPL, MSFT, NVDA, TSLA

**To customize:**
```python
# In main_multi_strategy.py or via API
watchlist_manager.get_watchlist("primary").add_ticker("GOOGL")
watchlist_manager.get_watchlist("primary").remove_ticker("TSLA")
```

### 2. Screener Watchlist (Dynamic)
Auto-populated every 30 minutes from stock screener.

**Criteria:**
- Price: $10 - $500
- Volume: > 1M shares/day
- Dollar volume: > $10M/day
- Momentum: +3% or more over 5 days
- Relative volume: > 1.3x average

**Top 10 momentum stocks** are automatically added.

### 3. Custom Watchlists
You can create strategy-specific watchlists:

```python
# Create a tech-focused watchlist
watchlist_manager.create_watchlist(
    name="tech_stocks",
    tickers=["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD"],
    description="Large cap tech"
)
```

---

## 🔍 Stock Screener

Runs automatically every 30 minutes to find high-probability setups.

### Screening Criteria

**Basic Filters:**
- Minimum price: $10
- Maximum price: $500
- Minimum volume: 1M shares/day
- Minimum dollar volume: $10M/day

**Opportunity Signals:**
1. **High Momentum:** +3%+ over 5 days
2. **High Relative Volume:** Current volume > 1.3x average
3. **Good Volatility:** ATR% between 1-5%

### Scoring System (0-100)

- **Momentum:** 40% weight
- **Relative Volume:** 30% weight
- **Volatility:** 30% weight

**Score > 50:** Strong opportunity
**Score > 70:** Exceptional opportunity
**Score < 30:** Weak signal (ignore)

### Manual Screening

```bash
# Run screener on specific universe
python scripts/run_screener.py --universe SP500 --min-score 60
```

---

## 🚀 Running the Bot

### Dry Run (Recommended First)

```bash
# Simulation mode - no real trades
python main_multi_strategy.py --dry-run --capital 10000

# With more detailed logging
python main_multi_strategy.py --dry-run --capital 10000 --log-level DEBUG
```

**Dry run:**
- Fetches real market data
- Generates real signals
- Simulates order execution
- Logs everything to `logs/trading_bot.log`

### Live Trading (CAUTION!)

```bash
# REAL MONEY - USE WITH EXTREME CAUTION
python main_multi_strategy.py --live --capital 10000
```

**Before going live:**
1. ✅ Backtest all strategies on 5+ years
2. ✅ Paper trade for 6+ months
3. ✅ Start with $1,000 micro-live
4. ✅ Verify all strategies pass quality checks
5. ✅ Test circuit breakers work

---

## ⚙️ Configuration

### Capital Allocation

```python
# $10,000 capital example
BotConfig.default(strategy="trend_following", capital=10_000.0)
```

**Defaults:**
- Max position size: 25% ($2,500)
- Max total exposure: 80% ($8,000)
- Cash reserve: 20% ($2,000)
- Max positions: 5 concurrent

### Risk Management

**Circuit Breakers:**
- Max daily loss: 2% of capital ($200 on $10k)
- Max consecutive losses: 3 trades
- Max trades per hour: 5 (prevents overtrading)

**Position Sizing:**
- 2% risk per trade (based on ATR stop loss)
- Volatility-adjusted (higher volatility = smaller position)

### Polling Frequency

```python
polling_interval_seconds = 300  # Check every 5 minutes
```

**Schedule:**
- Market regime: Every 60 minutes
- Stock screener: Every 30 minutes
- Position monitoring: Every 5 minutes
- Signal scanning: Every 5 minutes

---

## 📈 Monitoring & Logs

### Real-time Status

The bot logs status every cycle:

```
2026-02-09 10:00:00 [INFO] Status: Regime=BULL Strong Trend (Medium Vol), Active Strategies=2, Positions=3
```

### Log Files

**Location:** `logs/trading_bot.log`

**What's logged:**
- Market regime changes
- Strategy activation/deactivation
- Signals generated (all strategies)
- Trades executed
- Position updates
- Errors and warnings

### Daily Summary Email (Optional)

```python
# In main_multi_strategy.py
reporter = PerformanceReporter(email_enabled=True)
reporter.send_daily_summary()
```

---

## 🔧 Customization

### Adding a New Strategy

1. **Create strategy file:**
   ```python
   # autotrade/strategy/my_strategy.py
   from autotrade.strategy.base import Strategy, Signal

   class MyStrategy(Strategy):
       def is_compatible_with_regime(self, regime):
           # Define when strategy should be active
           return regime.is_bullish() and regime.volatility == VolatilityRegime.HIGH

       def generate_signals(self, ticker, data, regime):
           # Your signal logic
           pass

       def check_exit_conditions(self, ticker, entry_price, current_price, direction, days_held):
           # Your exit logic
           pass
   ```

2. **Register in bot:**
   ```python
   # In main_multi_strategy.py -> _initialize_strategies()
   my_strategy = MyStrategy(params=MyStrategyParams())
   self.strategy_manager.register_strategy(my_strategy)
   ```

### Adjusting Strategy Parameters

Edit `autotrade/config.py`:

```python
@dataclass(frozen=True)
class TrendFollowingParams:
    sma_fast: int = 50  # Try 20 for faster signals
    sma_slow: int = 200  # Try 100 for faster confirmation
    atr_stop_multiplier: float = 2.5  # Wider stops = less whipsaw
    # ... more parameters
```

---

## 📊 Performance Tracking

### Per-Strategy Metrics

```python
# Get strategy status
status = strategy_manager.get_strategy_status()
print(status)
```

**Output:**
```python
{
    "trend_following": {
        "active": True,
        "signals_today": 12,
        "trades_today": 3,
        "last_signal": "2026-02-09T14:30:00"
    },
    "mean_reversion": {
        "active": False,
        "signals_today": 0,
        "trades_today": 0,
        "last_signal": None
    }
}
```

### Portfolio Metrics

The `PerformanceReporter` tracks:
- Win rate per strategy
- Profit factor per strategy
- Average hold time
- Best/worst trades
- Regime-specific performance

---

## ⚠️ Common Issues

### Issue: "No signals generated"

**Cause:** Regime not compatible with any strategy
**Solution:** This is normal! In bear markets or uncertain conditions, staying in cash is correct.

### Issue: "Too many signals, not executing"

**Cause:** Circuit breaker limiting trades
**Solution:** Increase `max_trades_per_hour` in config

### Issue: "Strategy keeps switching"

**Cause:** Market regime fluctuating (choppy market)
**Solution:** This is expected during transitional periods. System will stabilize.

### Issue: "Screener finding no stocks"

**Cause:** Quiet market, low momentum
**Solution:** Normal during low volatility. System will find opportunities when they appear.

---

## 🎓 Best Practices

1. **Start Small**
   - Begin with $1,000-$2,000
   - Test for 1-3 months
   - Gradually increase capital

2. **Let It Run**
   - Don't micro-manage
   - Trust the regime detection
   - Some days will have 0 trades (normal!)

3. **Review Weekly**
   - Check which strategies are activating
   - Verify regime detection makes sense
   - Adjust parameters if needed

4. **Multiple Strategies = Diversification**
   - Trend following captures trends
   - Mean reversion profits from ranges
   - Momentum catches explosive moves
   - Together = smoother equity curve

5. **Monitor Market Regime**
   - Strong trends → Trend following + Momentum shine
   - Ranging markets → Mean reversion outperforms
   - Uncertain markets → Stay in cash (capital preservation)

---

## 📝 Example Daily Workflow

**9:00 AM:** Bot starts, waits for market open

**9:30 AM:** Market opens
- Bot detects market regime (regime updated hourly)
- Activates compatible strategies
- Scans primary watchlist for signals

**10:00 AM:** Screener runs
- Scans 30+ stocks for opportunities
- Updates dynamic watchlist with top 10

**10:05 AM:** Signal detected
- Momentum breakout signal on NVDA
- Executes trade: Buy 50 shares @ $875.50

**11:00 AM:** Regime re-check
- Still bull market + strong trend
- Trend following & momentum remain active

**2:00 PM:** Exit signal
- NVDA momentum fading (volume dried up)
- Executes: Sell 50 shares @ $882.30
- Profit: +$340 (0.8% gain)

**4:00 PM:** Market closes
- Bot enters idle state
- Daily summary logged
- Positions held overnight (if swing trades)

---

## 🚀 Next Steps

1. **Run in dry-run for 1 week**
   - Observe regime changes
   - Watch which strategies activate
   - Verify signal quality

2. **Backtest each strategy individually**
   - Test trend following on 2020-2024
   - Test mean reversion on choppy periods (2022)
   - Test momentum on strong trends (2023)

3. **Paper trade for 6+ months**
   - Compare performance to backtest
   - Ensure strategies behave as expected
   - Track regime accuracy

4. **Start micro-live**
   - $1,000 capital
   - Run for 3 months
   - Compare to paper trading

5. **Scale up gradually**
   - Increase capital 10-20% per month
   - Only if meeting performance targets
   - Stop if Sharpe < 1.0

---

## 📚 Further Reading

- [STRATEGIC_PIVOT.md](STRATEGIC_PIVOT.md) - Why multi-strategy approach
- [RUN_BACKTEST.md](../RUN_BACKTEST.md) - Backtest each strategy
- [QUICK_START_NEW.md](QUICK_START_NEW.md) - Setup guide

---

**Remember:** No strategy works in all markets. The multi-strategy approach ensures you have the right tool for each market condition! 🎯
