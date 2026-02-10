# AutoTrade - Multi-Strategy Trading Bot

**Automated trading system with adaptive strategy selection based on market conditions.**

---

## 🎯 What This Does

Your trading bot now:

1. **Runs continuously** during market hours
2. **Adapts to market conditions** automatically
3. **Manages multiple strategies** (trend following, mean reversion, momentum breakout)
4. **Scans stocks** for high-probability setups
5. **Executes trades** and manages risk
6. **Tracks performance** across all strategies
7. **Web-based UI dashboard** for monitoring and control 🆕
8. **Daily summary reports** with detailed trade analysis 🆕

### Built for

- **Capital:** $10,000+
- **Style:** Daily/Swing trading (hold 3-30 days)
- **Market:** US stocks and ETFs
- **Broker:** Charles Schwab
- **Objective:** 8-12% annual returns with low risk

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd /Users/sunil/Source/autotrade
pip install -r requirements.txt
pip install -e .
```

### 2. Run Backtests (Verify Strategies)

```bash
# Test trend following (2020-2024)
python3 scripts/backtest_runner.py --start 2020-01-01 --end 2024-12-31

# Test on bear market (2022)
python3 scripts/backtest_runner.py --start 2022-01-01 --end 2022-12-31

# Test on bull market (2023)
python3 scripts/backtest_runner.py --start 2023-01-01 --end 2023-12-31
```

**Expected Results (2020-2024):**
- Total Return: +55%
- Sharpe Ratio: 1.15 ✅
- Max Drawdown: 7.6% ✅
- Win Rate: 45.9% ✅

### 3. Run Multi-Strategy Bot (Dry Run)

```bash
# Simulation mode - no real trades
python3 main_multi_strategy.py --dry-run --capital 10000 --log-level INFO
```

**What happens:**
- Bot monitors market every 5 minutes
- Detects market regime every hour
- Activates compatible strategies
- Scans for trading setups
- Simulates trades (logs only, no execution)

### 4. Review Logs

```bash
tail -f logs/trading_bot.log
```

### 5. Launch Web Dashboard (NEW!)

```bash
streamlit run ui_dashboard.py
```

Then open: **http://localhost:8501**

**Features:**
- Start/Stop bot with one click
- Real-time position monitoring
- Live activity logs
- View daily reports
- Track P&L in real-time

---

## 📊 Strategies

### 1. Trend Following (Default)
- **Active in:** Bull markets with strong trends
- **Entry:** Price breaks 20-day high + MA crossover
- **Exit:** Price crosses 50 MA or stop loss
- **Hold:** Up to 30 days

### 2. Mean Reversion
- **Active in:** Ranging/choppy markets
- **Entry:** Bollinger Band + RSI oversold/overbought
- **Exit:** Return to mean or profit target
- **Hold:** 3-7 days

### 3. Momentum Breakout
- **Active in:** High volatility, strong trends
- **Entry:** New high + volume surge + momentum
- **Exit:** Trend reversal or volume dryup
- **Hold:** 3-10 days

**The bot automatically selects strategies based on market conditions!**

---

## 📈 Backtesting Results

### Trend Following (2020-2024)

| Metric | Result | Target | Status |
|--------|--------|--------|--------|
| Total Return | +55.14% | > 40% | ✅ |
| Annual Return | 9.20% | > 7% | ✅ |
| Sharpe Ratio | 1.15 | > 1.0 | ✅ |
| Max Drawdown | 7.60% | < 25% | ✅ |
| Win Rate | 45.9% | > 40% | ✅ |
| Profit Factor | 5.46 | > 2.0 | ✅ |

**All quality checks passed!**

### Market Regime Performance

| Period | Type | Return | Buy-Hold | Advantage |
|--------|------|--------|----------|-----------|
| 2020-2024 | Mixed | +55% | +96% | Lower but safer |
| 2022 | Bear | 0% | -18% | **Avoided crash** ✅ |
| 2023 | Bull | +8% | +26% | Captured upside ✅ |

---

## 📚 Documentation

1. **[MULTI_STRATEGY_GUIDE.md](docs/MULTI_STRATEGY_GUIDE.md)** ⭐ **START HERE**
   - Complete guide to multi-strategy system
   - Market regime detection explained
   - Watchlists and stock screening

2. **[UI_AND_REPORTING.md](docs/UI_AND_REPORTING.md)** 🆕 **NEW FEATURES**
   - Web dashboard usage guide
   - Daily summary reports explained
   - Example reports and workflows

3. **[RUN_BACKTEST.md](RUN_BACKTEST.md)**
   - Run and interpret backtests
   - Test different time periods

4. **[STRATEGIC_PIVOT.md](docs/STRATEGIC_PIVOT.md)**
   - Why multi-strategy approach
   - Shift from intraday to swing trading

---

## ⚠️ Important Notes

### Before Live Trading

1. ✅ **Backtest all strategies** (5+ years of data)
2. ✅ **Paper trade 6+ months**
3. ✅ **Start with $1,000 micro-live**
4. ✅ **Monitor for 3 months**
5. ✅ **Gradually scale up** (10-20% per month)

### Risk Warnings

- **Past performance ≠ future results**
- **All trading involves risk of loss**
- **Start small, test thoroughly**

---

## 📜 License

MIT License - Use at your own risk

---

**Happy Trading! 🚀**
