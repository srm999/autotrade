# Strategic Pivot: Sustainable Trading System

**Date**: February 2026
**Capital**: $10,000
**Objective**: Build evidence-based trading system with realistic profit expectations

---

## 🎯 Strategic Changes

### From → To

| Aspect | Old Approach | New Approach |
|--------|-------------|--------------|
| **Timeframe** | Intraday (1-minute) | Daily/Swing (EOD signals, hold 2-10 days) |
| **Instruments** | TQQQ/SQQQ (3x leveraged) | SPY, QQQ, Large Caps (non-leveraged) |
| **Capital** | $1,500 | $10,000 |
| **Strategies** | Mean reversion pairs | Trend following + Mean reversion |
| **Execution** | Market orders, 60s polling | Limit orders, EOD execution |
| **Position Size** | Fixed $1,000 | Volatility-adjusted (2% risk per trade) |
| **Max Daily Loss** | $500 (33%!) | $200 (2% of capital) |
| **Focus** | High frequency, low edge | Lower frequency, higher edge |

---

## 📊 New Portfolio Strategy

### Core Philosophy
- **Diversification**: Trade 5-8 positions simultaneously
- **Risk Management**: 2% risk per trade, 8% max portfolio risk
- **Evidence-Based**: Only trade strategies with backtested Sharpe > 1.0
- **Cost-Aware**: Account for 0.10% transaction costs per side

### Position Sizing Framework

```
Capital: $10,000
Risk per trade: 2% = $200
Max positions: 5 simultaneous
Max portfolio exposure: 80% = $8,000
Reserve cash: 20% = $2,000
```

**Volatility-Adjusted Sizing**:
```
Position Size = (Capital × Risk%) / (Entry Price × ATR% × ATR_Multiplier)

Example for SPY @ $500, ATR = $10 (2%):
Position Size = ($10,000 × 2%) / ($500 × 2% × 2) = $200 / $20 = 10 shares
Notional = $5,000
Stop Loss = 2 × ATR = $20 below entry
```

---

## 🎲 Strategy Portfolio (4 Strategies)

### Strategy 1: Trend Following (40% allocation)
**Instruments**: SPY, QQQ, IWM
**Timeframe**: Daily
**Logic**:
- Entry: Price > 50 MA AND 50 MA > 200 MA AND price breaks 20-day high
- Exit: Price < 10 MA OR stop loss (2 × ATR)
- Hold: 5-30 days

**Why it works**:
- 40+ years of academic research (Faber, Hurst, et al.)
- Captures sustained trends
- Lower win rate (~40%) but high profit factor (2.5+)

**Expected Metrics** (based on historical research):
- Sharpe: 0.8 - 1.2
- Max DD: 15-25%
- Win rate: 35-45%
- Avg hold: 15-20 days

---

### Strategy 2: Mean Reversion Large Caps (30% allocation)
**Instruments**: AAPL, MSFT, GOOGL, AMZN, NVDA
**Timeframe**: Daily
**Logic**:
- Entry: Price < 20 MA by > 2 std devs AND RSI < 30 AND stock > 200 MA
- Exit: Price > 20 MA OR stop loss (1.5 × ATR)
- Hold: 2-7 days

**Why it works**:
- Large caps mean-revert faster than indices
- Institutional support provides floor
- High win rate (~65%) but smaller winners

**Expected Metrics**:
- Sharpe: 1.0 - 1.5
- Max DD: 10-15%
- Win rate: 60-70%
- Avg hold: 3-5 days

---

### Strategy 3: Sector Rotation (20% allocation)
**Instruments**: XLF, XLE, XLK, XLV, XLI, XLY
**Timeframe**: Weekly
**Logic**:
- Rank sectors by 3-month momentum
- Long top 2 sectors
- Rebalance weekly
- Stop loss: 10% per position

**Why it works**:
- Sectors rotate through economic cycles
- Relative strength persists
- Lower turnover = lower costs

**Expected Metrics**:
- Sharpe: 0.6 - 1.0
- Max DD: 15-20%
- Win rate: 55-65%
- Trades per month: 2-4

---

### Strategy 4: Volatility Breakout (10% allocation)
**Instruments**: SPY, QQQ
**Timeframe**: Daily
**Logic**:
- Wait for VIX spike > 30
- Buy when VIX drops below 25 AND price > yesterday's high
- Exit: 5 days OR 10% profit OR VIX > 30 again
- Hold: 3-10 days

**Why it works**:
- Markets overshoots on fear
- VIX mean-reverts
- High profit potential on low frequency

**Expected Metrics**:
- Sharpe: 1.5 - 2.5 (but only 3-8 trades/year)
- Max DD: 8-12%
- Win rate: 70-80%
- Trades per year: 3-8

---

## 🏗️ Implementation Plan

### Phase 1: Infrastructure (Week 1-2)
- [x] Create strategic pivot document
- [ ] Build backtesting framework
- [ ] Implement transaction cost modeling
- [ ] Add limit order support
- [ ] Create volatility-based position sizer
- [ ] Build portfolio-level risk monitor

### Phase 2: Strategy Implementation (Week 3-4)
- [ ] Implement Trend Following strategy
- [ ] Implement Mean Reversion strategy
- [ ] Implement Sector Rotation strategy
- [ ] Implement Volatility Breakout strategy
- [ ] Create strategy portfolio manager

### Phase 3: Backtesting (Week 5-6)
- [ ] Backtest each strategy individually (2018-2025)
- [ ] Backtest portfolio combination
- [ ] Optimize parameters (but avoid overfitting)
- [ ] Walk-forward testing
- [ ] Monte Carlo simulation for drawdowns

### Phase 4: Paper Trading (Month 2-8)
- [ ] Deploy paper trading with EOD execution
- [ ] Track vs backtest expectations
- [ ] Monitor slippage and costs
- [ ] Refine strategies based on live data
- [ ] Build confidence in system

### Phase 5: Micro-Live (Month 9+)
- [ ] Start with $1,000 (10% of capital)
- [ ] Run alongside paper trading
- [ ] Compare results for 3 months
- [ ] Scale up gradually if successful

---

## 📈 Realistic Performance Expectations

### Portfolio-Level (All 4 Strategies Combined)

**Optimistic Scenario** (75th percentile):
- Annual Return: 12-18%
- Sharpe Ratio: 1.2 - 1.5
- Max Drawdown: 12-18%
- Win Rate: 55-60%
- Trades per month: 8-15

**Realistic Scenario** (50th percentile):
- Annual Return: 8-12%
- Sharpe Ratio: 0.8 - 1.2
- Max Drawdown: 15-25%
- Win Rate: 50-55%
- Trades per month: 8-15

**Conservative Scenario** (25th percentile):
- Annual Return: 3-8%
- Sharpe Ratio: 0.5 - 0.8
- Max Drawdown: 20-30%
- Win Rate: 45-50%
- Trades per month: 8-15

**On $10,000 Capital**:
- Optimistic: $1,200 - $1,800/year = $100-150/month
- Realistic: $800 - $1,200/year = $65-100/month
- Conservative: $300 - $800/year = $25-65/month

**Still not "regular income"** but more sustainable than intraday leveraged ETF trading.

---

## 🛡️ Risk Management Rules

### Position-Level
1. **Max risk per trade**: 2% of capital ($200)
2. **Stop loss**: Always use 1.5-2.5 × ATR
3. **Position size**: Volatility-adjusted using ATR
4. **Max single position**: 25% of capital ($2,500)

### Portfolio-Level
1. **Max simultaneous positions**: 5
2. **Max portfolio exposure**: 80% ($8,000)
3. **Max correlated positions**: 3 (avoid all tech or all SPY-correlated)
4. **Daily loss limit**: $200 (2% of capital)
5. **Weekly loss limit**: $500 (5% of capital)

### Strategy-Level
1. **Min backtest Sharpe**: 1.0 before deployment
2. **Min backtest period**: 5 years
3. **Out-of-sample testing**: Required (20% holdout)
4. **Max strategy allocation**: 40%

---

## 📚 Key Metrics to Track

### Performance Metrics
- Total Return (%)
- Sharpe Ratio (risk-adjusted return)
- Sortino Ratio (downside risk)
- Max Drawdown (%)
- Calmar Ratio (return / max DD)
- Win Rate (%)
- Profit Factor (gross profit / gross loss)
- Average Win vs Average Loss

### Operational Metrics
- Trades per month
- Average hold time
- Slippage vs backtest
- Commission costs
- Actual vs expected Sharpe
- Strategy correlations

### Risk Metrics
- Daily VaR (Value at Risk, 95%)
- Portfolio beta to SPY
- Correlation between strategies
- Largest daily loss
- Largest weekly loss
- Consecutive losses

---

## 🚫 What NOT to Do

1. ❌ Don't over-optimize strategies on historical data
2. ❌ Don't trade without stop losses
3. ❌ Don't increase position size after wins (gambler's fallacy)
4. ❌ Don't decrease position size after losses (loss aversion)
5. ❌ Don't add new strategies without backtesting
6. ❌ Don't trade on margin (at least initially)
7. ❌ Don't revenge trade after losses
8. ❌ Don't check portfolio every hour (reduces decision quality)
9. ❌ Don't trade on news or emotions
10. ❌ Don't expect "regular income" - expect volatility

---

## 🎓 Recommended Reading

### Must-Read Books
1. **"Evidence-Based Technical Analysis"** - David Aronson (statistical rigor)
2. **"Following the Trend"** - Andreas Clenow (trend following)
3. **"Quantitative Trading"** - Ernest Chan (practical implementation)
4. **"Trading Systems"** - Tomasini & Jaekle (system development)

### Research Papers
1. **"A Quantitative Approach to Tactical Asset Allocation"** - Meb Faber (trend following foundation)
2. **"Do Industries Explain Momentum?"** - Moskowitz & Grinblatt (sector momentum)
3. **"Facts and Fantasies About Commodity Futures"** - Gorton & Rouwenhorst

### Online Resources
1. **QuantConnect** - Backtesting platform and education
2. **Alpha Architect** - Evidence-based strategy research
3. **Two Sigma** - Academic research papers

---

## 📞 Decision Points

### When to Continue Paper Trading
- Sharpe ratio < 1.0 in live paper trading
- Slippage > 0.20% per trade
- Drawdown > 30%
- Paper results diverge significantly from backtest

### When to Start Micro-Live
- 6+ months successful paper trading
- Sharpe ratio > 1.0 consistently
- Paper results match backtest expectations
- All systems stable and tested

### When to Scale Up
- 3+ months successful micro-live trading
- Returns match paper trading
- Emotional control maintained
- No system failures or errors

### When to Stop/Pivot
- 12 months negative returns despite refinements
- Sharpe ratio < 0.3 persistently
- Unable to maintain discipline
- Better opportunities elsewhere (career, business, etc.)

---

## ✅ Success Criteria (12 Months)

### Minimum Success
- Paper trading Sharpe > 0.8
- Max drawdown < 25%
- Backtest matches paper within 20%
- No major system failures

### Good Success
- Paper trading Sharpe > 1.0
- Max drawdown < 20%
- Positive returns in 8/12 months
- System runs reliably

### Excellent Success
- Paper trading Sharpe > 1.3
- Max drawdown < 15%
- Positive returns in 9/12 months
- Ready for micro-live deployment

---

**Remember**: The goal is to build a sustainable, evidence-based system. Not to get rich quick.

Most profitable algo traders spent 3-5 years before consistent success. Patience and discipline are your biggest edges.
