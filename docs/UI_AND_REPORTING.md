# UI Dashboard and Daily Reporting Guide

## Overview

Your trading bot now includes two powerful features:

1. **Web-based UI Dashboard** - Monitor and control the bot from your browser
2. **Daily Summary Reports** - Comprehensive end-of-day trading reports

---

## 🖥️ UI Dashboard

### Features

The dashboard provides:
- **Start/Stop controls** with capital configuration
- **Real-time status** display (market regime, active strategies, positions)
- **Live position monitoring** with P&L tracking
- **Activity log viewer** with auto-refresh
- **Report browser** to view historical daily reports

### Starting the Dashboard

```bash
cd /Users/sunil/Source/autotrade
streamlit run ui_dashboard.py
```

The dashboard will open at: **http://localhost:8501**

### Using the Dashboard

#### 1. Sidebar Controls

**Trading Capital**
- Set your trading capital ($1,000 - $1,000,000)
- Default: $10,000

**Dry Run Mode**
- ✅ Checked: Simulation mode (no real trades)
- ❌ Unchecked: Live trading (**real money at risk**)

**Start/Stop Buttons**
- **▶️ Start**: Begin bot operation
- **⏹️ Stop**: Gracefully stop bot (closes positions, generates report)

**Status Indicator**
- 🟢 Green: Bot running
- 🔴 Red: Bot stopped

#### 2. Dashboard Tab

Shows:
- **Market Regime**: Current market conditions
- **Active Strategies**: Which strategies are currently trading
- **Open Positions**: Number of positions held
- **Status**: Running/Stopped

#### 3. Positions Tab

Real-time position monitoring:
- Ticker
- Strategy used
- Direction (LONG/SHORT)
- Quantity
- Entry price
- Current price
- P&L ($)
- P&L (%)
- Days held

#### 4. Logs Tab

Activity log with:
- Recent bot activities
- Auto-refresh option (updates every 5 seconds)
- Last 20 lines from `logs/trading_bot.log`

#### 5. Reports Tab

Browse and view:
- All generated daily summary reports
- Select report from dropdown
- View full report content

---

## 📊 Daily Summary Reports

### What's Included

Each daily report contains:

1. **Session Info**
   - Session start time
   - Report generation time

2. **Market Regime Changes**
   - Timeline of regime changes throughout the day
   - Active strategies for each regime

3. **Trading Activity**
   - All trades executed (buys and sells)
   - Grouped by ticker
   - Entry/exit prices
   - Strategy used
   - P&L for closed positions
   - Summary statistics (total trades, total P&L)

4. **Signals Generated**
   - All signals from all strategies
   - Executed vs. ignored signals
   - Grouped by strategy
   - Confidence levels

5. **Performance Summary**
   - Total trades (all-time)
   - Completed trades
   - Win rate
   - Total P&L
   - Average P&L per trade

6. **Errors** (if any)
   - Timestamp
   - Error type
   - Error message
   - Context

### Report Location

Reports are saved to:
```
reports/daily_summary_YYYY-MM-DD.txt
```

Example:
```
reports/daily_summary_2024-02-09.txt
```

### When Reports are Generated

Reports are automatically generated:

1. **End of trading day** (after 4:00 PM ET)
2. **On bot shutdown** (manual stop or Ctrl+C)

### Viewing Reports

**Via Dashboard:**
- Go to "Reports" tab
- Select report from dropdown
- View in text area

**Via Command Line:**
```bash
cat reports/daily_summary_2024-02-09.txt
```

**Via File Explorer:**
- Navigate to `reports/` folder
- Open `.txt` file in any text editor

---

## 📋 Example Daily Report

```
================================================================================
AUTOTRADE - DAILY TRADING SUMMARY
Date: Friday, February 09, 2024
================================================================================

SESSION INFO
--------------------------------------------------------------------------------
Session started: 09:30:15
Report generated: 16:05:32

MARKET REGIME CHANGES
--------------------------------------------------------------------------------
[09:30:15] BULL Strong Trend (Medium Vol)
           Active strategies: Trend Following, Momentum Breakout
[14:15:22] BULL Weak Trend (Low Vol)
           Active strategies: Trend Following

TRADING ACTIVITY
--------------------------------------------------------------------------------

AAPL:
  [10:25:33] BUY 50 shares @ $175.25 (Momentum Breakout)
  [14:45:18] SELL 50 shares @ $182.50 (Momentum Breakout) - P&L: +$362.50

NVDA:
  [11:15:42] BUY 25 shares @ $485.00 (Trend Following)

Total trades: 3 (2 buys, 1 sells)
Total P&L: +$362.50

SIGNALS GENERATED
--------------------------------------------------------------------------------
Total signals: 8
Executed: 3
Ignored: 5

Momentum Breakout:
  [10:25:30] AAPL - ENTRY (confidence: 85%) - ✓ EXECUTED
  [14:45:15] AAPL - EXIT (confidence: 75%) - ✓ EXECUTED

Mean Reversion:
  [11:30:22] MSFT - ENTRY (confidence: 45%) - ✗ Ignored

PERFORMANCE SUMMARY
--------------------------------------------------------------------------------
Total trades (all-time): 3
Completed trades: 1
Win rate: 100.0%
Total P&L (all-time): +$362.50
Average P&L per trade: +$362.50

ERRORS
--------------------------------------------------------------------------------
[12:15:33] ValueError (execute_trade): Insufficient funds for trade

================================================================================
End of Report
================================================================================
```

---

## 🧪 Testing the Features

### Test the Reporting

```bash
python3 scripts/test_reporting.py
```

This will:
- Simulate a trading day with various activities
- Generate signals, trades, regime changes
- Create a sample daily report
- Show you the report format

### Test the Dashboard

1. Start the dashboard:
   ```bash
   streamlit run ui_dashboard.py
   ```

2. Open browser to http://localhost:8501

3. Click "▶️ Start" with:
   - Capital: $10,000
   - Dry Run: ✅ Checked

4. Watch the dashboard update in real-time

5. Check "Reports" tab for generated reports

---

## 🎯 Workflow Example

### Typical Trading Day

**Morning (9:00 AM):**
```bash
streamlit run ui_dashboard.py
```
- Open dashboard
- Set capital: $10,000
- Enable Dry Run: Yes
- Click "▶️ Start"

**During Market Hours:**
- Monitor "Dashboard" tab for regime changes
- Check "Positions" tab for active trades
- Watch "Logs" tab for activity

**After Market Close (4:00 PM+):**
- Bot automatically generates daily report
- Check "Reports" tab to view summary
- Review trades, P&L, and strategy performance

**End of Day:**
- Click "⏹️ Stop"
- Final report generated with all positions closed
- Review report in `reports/` folder

---

## 🔧 Configuration

### Dashboard Port

Default: 8501

To change port:
```bash
streamlit run ui_dashboard.py --server.port 8502
```

### Report Directory

Default: `reports/`

To change in bot:
```python
reporter = PerformanceReporter(reports_dir="my_reports")
```

---

## 📝 Tips and Best Practices

### Dashboard

1. **Use Dry Run First**
   - Always test with dry run before live trading
   - Verify strategies work as expected

2. **Monitor Positions**
   - Check positions tab regularly
   - Watch P&L fluctuations
   - Understand why positions were entered

3. **Review Logs**
   - Enable auto-refresh during active trading
   - Look for errors or warnings
   - Verify regime changes make sense

### Reports

1. **Daily Review**
   - Read full report every day
   - Analyze what worked and what didn't
   - Track strategy performance over time

2. **Compare Reports**
   - Look at week-over-week performance
   - Identify patterns in winning/losing trades
   - Adjust strategy parameters if needed

3. **Archive Reports**
   - Reports are dated automatically
   - Keep for tax purposes
   - Use for strategy optimization

---

## ⚠️ Important Notes

### Dashboard

- **Single Instance**: Only run one bot instance at a time
- **Browser Caching**: Refresh browser if data looks stale
- **Background Operation**: Bot runs in background thread while dashboard updates

### Reports

- **Timezone**: All times in local timezone
- **P&L Accuracy**: Calculated from entry/exit prices (no slippage/fees in dry run)
- **Signal Tracking**: Tracks all signals, even if not executed

---

## 🚀 Next Steps

1. **Run Test**: `python3 scripts/test_reporting.py`
2. **Start Dashboard**: `streamlit run ui_dashboard.py`
3. **Paper Trade**: Run in dry mode for 1-2 weeks
4. **Review Reports**: Analyze daily performance
5. **Optimize**: Adjust strategies based on reports
6. **Go Live**: When confident, disable dry run (with caution!)

---

**Happy Trading! 🤖📊**
