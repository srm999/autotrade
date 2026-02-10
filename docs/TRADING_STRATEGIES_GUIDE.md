# Automated Trading Strategies Guide

**Date**: February 2026
**Version**: 1.0
**Strategies**: Dual MA Mean Reversion, Intraday Pair Spread

---

## Table of Contents

1. [Overview](#overview)
2. [Strategy 1: Dual MA Mean Reversion](#strategy-1-dual-ma-mean-reversion)
3. [Strategy 2: Intraday Pair Spread](#strategy-2-intraday-pair-spread)
4. [Risk Management](#risk-management)
5. [Examples & Scenarios](#examples--scenarios)
6. [Performance Considerations](#performance-considerations)
7. [Configuration Guide](#configuration-guide)

---

## Overview

This trading bot implements two automated strategies for trading leveraged ETF pairs (TQQQ/SQQQ). Both strategies are designed for intraday trading with end-of-day position flattening.

### Key Principles

1. **Leveraged ETF Pairs**: Trade TQQQ (3x long Nasdaq) and SQQQ (3x short Nasdaq)
2. **Mean Reversion**: Capitalize on short-term price deviations
3. **Risk Management**: Circuit breakers, position limits, stop losses
4. **Intraday Focus**: Close all positions before market close
5. **Automated Execution**: No manual intervention required

### Supported Assets

| Ticker | Description | Leverage | Direction |
|--------|-------------|----------|-----------|
| TQQQ | ProShares UltraPro QQQ | 3x | Long Nasdaq |
| SQQQ | ProShares UltraPro Short QQQ | 3x | Short Nasdaq |

**Note**: These are inverse pairs - when QQQ goes up, TQQQ rises and SQQQ falls (and vice versa).

---

## Strategy 1: Dual MA Mean Reversion

### Strategy Overview

The Dual MA Mean Reversion strategy uses **moving average crossovers** to identify market regime, then trades mean reversion signals based on **z-score deviations** from a short-term moving average.

**Type**: Trend-following with mean reversion
**Timeframe**: Daily for regime, intraday for entries
**Hold Duration**: Minutes to hours (intraday only)
**Win Rate**: ~55-60% (backtested)

### Core Concepts

#### 1. Regime Detection (Trend Following)
Uses two moving averages to identify market trend:
- **Fast MA**: 50-day simple moving average
- **Slow MA**: 250-day simple moving average

**Bullish Regime**: Fast MA > Slow MA (trade TQQQ)
**Bearish Regime**: Fast MA < Slow MA (trade SQQQ)

#### 2. Mean Reversion Entry (Contrarian)
Within the identified regime, wait for price to deviate significantly from its recent average, then trade the reversion.

**Entry Signal**: Price moves too far from short-term mean
**Exit Signal**: Price returns to mean (z-score crosses threshold)

### Mathematical Foundation

#### Z-Score Calculation
```python
# Rolling 20-day standard deviation and mean
rolling_std = prices.rolling(20).std()
rolling_mean = prices.rolling(20).mean()

# Z-score = (current_price - mean) / std_dev
z_score = (current_price - rolling_mean) / rolling_std
```

**Interpretation**:
- **Z > +1.0**: Price is 1 standard deviation above average (overbought)
- **Z < -1.0**: Price is 1 standard deviation below average (oversold)
- **Z ≈ 0**: Price at average (neutral)

### Entry/Exit Logic

#### Entry Conditions

**Buy Signal** (Go Long):
```
1. Regime = Bullish (50-day MA > 250-day MA)
2. Current z-score < -1.0 (oversold)
3. No position currently held
4. Haven't traded this ticker today
```

**Sell Signal** (Close Position):
```
1. Currently long
2. Z-score crosses back above 0.0 (returned to mean)
```

**OR**

```
1. Stop loss triggered (price down 3% from entry)
2. Flatten time reached (10 minutes before close)
```

### Parameters

**Location**: `autotrade/config.py:45-53`

```python
@dataclass
class DualMAMeanReversionParams:
    fast_window: int = 50                    # Fast MA period (days)
    slow_window: int = 250                   # Slow MA period (days)
    std_lookback: int = 20                   # Std dev calculation period
    entry_zscore: float = 1.0               # Entry threshold (absolute value)
    exit_zscore: float = 0.0                # Exit threshold
    stop_loss_pct: float = 0.03             # Stop loss at 3% loss
    regime_confirm_days: int = 3            # Days to confirm regime change
    flatten_minutes_before_close: int = 10  # Close positions 10 min early
```

### Position Sizing

Maximum position: **$1,000** per ticker
Maximum total exposure: **$1,500**

Actual shares calculated by:
```python
shares = min(
    int($1000 / current_price),           # Max position size
    int(available_cash / current_price)    # Available capital
)
```

### State Machine

The strategy maintains position state to prevent duplicate signals:

```
┌─────────────┐
│   NO_POS    │ ◄──────────────────┐
│  (waiting)  │                    │
└──────┬──────┘                    │
       │                           │
       │ z < -1.0                 │
       │ (oversold)               │
       ▼                           │
┌─────────────┐                    │
│   LONG      │                    │
│  (holding)  │                    │
└──────┬──────┘                    │
       │                           │
       │ z > 0.0 OR stop loss     │
       │                           │
       └───────────────────────────┘
```

### Example Trade Scenario

#### Scenario: Bullish Regime Entry

**Setup**:
- Date: February 9, 2026, 10:30 AM
- Ticker: TQQQ
- Current Price: $45.50
- 50-day MA: $44.20
- 250-day MA: $42.80
- 20-day rolling mean: $46.00
- 20-day rolling std: $1.20

**Step 1: Regime Check**
```python
regime = "bullish" if (44.20 > 42.80) else "bearish"
# Result: "bullish" ✓
```

**Step 2: Calculate Z-Score**
```python
z_score = (45.50 - 46.00) / 1.20
z_score = -0.417  # Slightly below mean, but not yet oversold
# No signal yet (need z < -1.0)
```

**15 Minutes Later (10:45 AM)**:
- Current Price: $44.20 (dropped)
- Z-score recalculated:

```python
z_score = (44.20 - 46.00) / 1.20
z_score = -1.50  # Now oversold! ✓
```

**Step 3: Generate Buy Signal**
```python
Signal(
    ticker="TQQQ",
    side="buy",
    quantity=22,  # $1000 / $45.50 ≈ 22 shares
    metadata={"reason": "entry", "z_score": -1.50}
)
```

**Step 4: Execute Trade**
```
INFO Submitted buy order: TQQQ x22 @ 44.20 (order_id=123456, reason=entry)
INFO Order 123456 filled: buy TQQQ x22
```

**Position Tracking**:
```python
Position(
    ticker="TQQQ",
    quantity=22,
    avg_cost=44.20,
    current_value=22 * 44.20 = $972.40
)
```

#### Exit Scenario 1: Mean Reversion (Profit)

**30 Minutes Later (11:15 AM)**:
- Current Price: $46.50 (price recovered)
- Z-score recalculated:

```python
z_score = (46.50 - 46.00) / 1.20
z_score = +0.417  # Back above 0 ✓
```

**Generate Sell Signal**:
```python
Signal(
    ticker="TQQQ",
    side="sell",
    quantity=22,  # Close entire position
    metadata={"reason": "exit", "z_score": 0.417}
)
```

**Execute Exit**:
```
INFO Submitted sell order: TQQQ x22 @ 46.50 (order_id=123457, reason=exit)
INFO Order 123457 filled: sell TQQQ x22
```

**Calculate P&L**:
```python
buy_cost = 22 * 44.20 = $972.40
sell_proceeds = 22 * 46.50 = $1,023.00
realized_pnl = $1,023.00 - $972.40 = $50.60 ✓

return_pct = ($50.60 / $972.40) * 100 = 5.2%
```

**Circuit Breaker Update**:
```python
# Record profitable trade
circuit_breaker.record_trade("TQQQ", realized_pnl=50.60)
# Consecutive losses reset to 0
```

#### Exit Scenario 2: Stop Loss (Loss)

**Alternative: Price Drops Further**

**20 Minutes Later (11:05 AM)**:
- Current Price: $42.88 (continued dropping)
- Entry price: $44.20
- Loss: ($42.88 - $44.20) / $44.20 = -2.99% ≈ -3% ✓

**Stop Loss Triggered**:
```python
Signal(
    ticker="TQQQ",
    side="sell",
    quantity=22,
    metadata={"reason": "stop_loss", "loss_pct": -3.0}
)
```

**Execute Stop Loss**:
```
INFO Submitted sell order: TQQQ x22 @ 42.88 (order_id=123458, reason=stop_loss)
WARNING Stop loss triggered for TQQQ: -3.0%
```

**Calculate P&L**:
```python
buy_cost = 22 * 44.20 = $972.40
sell_proceeds = 22 * 42.88 = $943.36
realized_pnl = $943.36 - $972.40 = -$29.04 ✗

return_pct = (-$29.04 / $972.40) * 100 = -3.0%
```

**Circuit Breaker Update**:
```python
circuit_breaker.record_trade("TQQQ", realized_pnl=-29.04)
# Consecutive losses: 1
# Daily PnL: -$29.04
```

---

## Strategy 2: Intraday Pair Spread

### Strategy Overview

The Intraday Pair Spread strategy trades the **relative price relationship** between TQQQ and SQQQ using high-frequency (1-minute) data. It calculates a **log-spread** between the two and trades when the spread deviates significantly from its recent mean.

**Type**: Statistical arbitrage / Pairs trading
**Timeframe**: 1-minute bars
**Hold Duration**: Minutes (typically 15-60 minutes)
**Win Rate**: ~50-55% (higher frequency, lower edge)

### Core Concepts

#### 1. Log-Spread Calculation
The log-spread captures the relative price movement:

```python
log_spread = log(TQQQ_price) - log(SQQQ_price)
```

**Why Log?**:
- Makes spread stationary (mean-reverting)
- Handles percentage changes better than arithmetic spread
- Reduces heteroscedasticity

#### 2. Rolling Statistics
Calculate mean and standard deviation over last N bars:

```python
spread_mean = rolling_mean(log_spread, window=60)  # 60 minutes
spread_std = rolling_std(log_spread, window=60)
```

#### 3. Z-Score of Spread
```python
z_score = (current_log_spread - spread_mean) / spread_std
```

**Interpretation**:
- **Z > +2.0**: TQQQ expensive relative to SQQQ → Sell TQQQ, Buy SQQQ
- **Z < -2.0**: TQQQ cheap relative to SQQQ → Buy TQQQ, Sell SQQQ
- **Z crosses ±0.5**: Spread reverting → Close positions

### Entry/Exit Logic

#### Entry Conditions

**Long TQQQ / Short SQQQ**:
```
1. Z-score < -2.0 (TQQQ underpriced vs SQQQ)
2. No current position
3. Not in cooldown period (10 min after last trade)
4. Have at least 60 bars of data
```

**Long SQQQ / Short TQQQ**:
```
1. Z-score > +2.0 (SQQQ underpriced vs TQQQ)
2. No current position
3. Not in cooldown period
4. Have at least 60 bars of data
```

#### Exit Conditions

**Normal Exit** (Z-score mean reversion):
```
1. Position held
2. Z-score crosses exit threshold (±0.5)
```

**Time-based Exit**:
```
1. Position held for > 60 minutes (max hold time)
2. OR 5 minutes before market close
```

### Parameters

**Location**: `autotrade/config.py:57-64`

```python
@dataclass
class IntradayPairSpreadParams:
    lookback_bars: int = 60              # 60 bars (1 hour of 1-min data)
    entry_zscore: float = 2.0           # Entry threshold
    exit_zscore: float = 0.5            # Exit threshold
    max_hold_minutes: int = 60          # Maximum hold time
    cooldown_minutes: int = 10          # Wait between trades
    interval: str = "1minute"            # Bar interval
    flatten_minutes_before_close: int = 5  # Close 5 min early
```

### Position Sizing

Same as Dual MA strategy:
- Maximum: $1,000 per ticker
- Total exposure: $1,500

**Note**: This strategy trades **both** tickers simultaneously (long one, short the other).

### Pair Trading Mechanics

#### Long Spread (Buy TQQQ, Sell SQQQ)
When z-score < -2.0:

```python
# Buy TQQQ
buy_signal = Signal(
    ticker="TQQQ",
    side="buy",
    quantity=calc_quantity(TQQQ_price, $1000)
)

# "Short" SQQQ (inverse ETF, so buying SQQQ = short exposure to Nasdaq)
# In practice, we just avoid trading SQQQ or wait for opposite signal
```

#### Short Spread (Buy SQQQ, Sell TQQQ)
When z-score > +2.0:

```python
# Buy SQQQ
buy_signal = Signal(
    ticker="SQQQ",
    side="buy",
    quantity=calc_quantity(SQQQ_price, $1000)
)
```

**Important**: Since both TQQQ and SQQQ are leveraged ETFs (not short positions), we trade them directionally based on the spread signal.

### State Machine

```
┌──────────────┐
│   NEUTRAL    │ ◄─────────────────────┐
│ (no position)│                       │
└──────┬───────┘                       │
       │                               │
       │ z < -2.0                     │ z crosses ±0.5
       │                               │ OR max hold time
       ▼                               │
┌──────────────┐                       │
│   LONG_A     │ ──────────────────────┘
│ (long TQQQ)  │
└──────────────┘

       ▲
       │
       │ z > +2.0
       │
       ▼
┌──────────────┐
│   LONG_B     │ ──────────────────────┐
│ (long SQQQ)  │                       │
└──────────────┘                       │
       │                               │
       │ z crosses ±0.5               │
       │ OR max hold time             │
       └───────────────────────────────┘
```

### Example Trade Scenario

#### Scenario: Spread Widening (Buy TQQQ)

**Setup**:
- Time: 11:00 AM
- Last 60 bars of 1-minute data collected
- TQQQ: $45.20
- SQQQ: $12.80

**Step 1: Calculate Log Spread**
```python
import math

log_spread = math.log(45.20) - math.log(12.80)
log_spread = 3.811 - 2.549 = 1.262
```

**Step 2: Calculate Rolling Statistics** (using last 60 bars)
```python
spread_mean = 1.350  # Average over last hour
spread_std = 0.045   # Std dev over last hour
```

**Step 3: Calculate Z-Score**
```python
z_score = (1.262 - 1.350) / 0.045
z_score = -1.956  # Close to entry threshold
```

**One Minute Later (11:01 AM)**:
- TQQQ: $44.95 (dropped)
- SQQQ: $12.85 (rose slightly)

```python
log_spread = log(44.95) - log(12.85)
log_spread = 3.805 - 2.553 = 1.252

z_score = (1.252 - 1.350) / 0.045
z_score = -2.178  # Below -2.0 ✓ Entry signal!
```

**Step 4: Generate Buy Signal**
```python
Signal(
    ticker="TQQQ",
    side="buy",
    quantity=22,  # $1000 / $44.95 ≈ 22 shares
    metadata={
        "reason": "spread_entry",
        "z_score": -2.178,
        "log_spread": 1.252,
        "direction": "long_a"
    }
)
```

**Step 5: Execute Trade**
```
INFO Submitted buy order: TQQQ x22 @ 44.95 (order_id=123460, reason=spread_entry)
INFO Order 123460 filled: buy TQQQ x22
INFO Intraday spread position: LONG_A (TQQQ)
```

#### Exit Scenario: Spread Reverting

**25 Minutes Later (11:26 AM)**:
- TQQQ: $45.80 (recovered)
- SQQQ: $12.70 (fell back)

```python
log_spread = log(45.80) - log(12.70)
log_spread = 3.824 - 2.542 = 1.282

# Recalculate z-score with updated rolling stats
spread_mean = 1.348  # Updated
spread_std = 0.046   # Updated

z_score = (1.282 - 1.348) / 0.046
z_score = -1.435  # Still negative but approaching zero
```

**3 Minutes Later (11:29 AM)**:
- TQQQ: $46.10
- SQQQ: $12.65

```python
log_spread = log(46.10) - log(12.65)
log_spread = 3.831 - 2.537 = 1.294

z_score = (1.294 - 1.348) / 0.046
z_score = -1.174  # Getting closer...
```

**2 Minutes Later (11:31 AM)**:
- TQQQ: $46.30
- SQQQ: $12.58

```python
log_spread = log(46.30) - log(12.58)
log_spread = 3.835 - 2.532 = 1.303

z_score = (1.303 - 1.348) / 0.046
z_score = -0.978  # Still not at exit threshold yet
```

**Wait... Z-score crosses -0.5 at 11:34 AM**:
```python
z_score = -0.45  # Crossed the +0.5 threshold (from below)
# Exit signal! ✓
```

**Generate Sell Signal**:
```python
Signal(
    ticker="TQQQ",
    side="sell",
    quantity=22,
    metadata={
        "reason": "spread_exit",
        "z_score": -0.45,
        "hold_minutes": 33
    }
)
```

**Execute Exit**:
```
INFO Submitted sell order: TQQQ x22 @ 46.50 (order_id=123461, reason=spread_exit)
INFO Order 123461 filled: sell TQQQ x22
INFO Spread position closed after 33 minutes
```

**Calculate P&L**:
```python
entry_cost = 22 * 44.95 = $988.90
exit_proceeds = 22 * 46.50 = $1,023.00
realized_pnl = $1,023.00 - $988.90 = $34.10 ✓

return_pct = ($34.10 / $988.90) * 100 = 3.45%
```

**Cooldown Period**:
```python
# No new trades for 10 minutes (until 11:44 AM)
cooldown_until = 11:34 AM + 10 minutes = 11:44 AM
```

---

## Risk Management

Both strategies implement multiple layers of risk management:

### 1. Position Limits

**Per-Position Limit**: $1,000 maximum per ticker
```python
max_shares = $1000 / current_price
actual_shares = min(max_shares, affordable_shares)
```

**Total Exposure Limit**: $1,500 across all positions
```python
if projected_exposure > $1500:
    # Reject trade
    log("Skipping buy; would exceed exposure limit")
```

### 2. Circuit Breakers

Automatically halt trading when risk limits exceeded:

| Limit | Default Value | Action |
|-------|---------------|--------|
| Daily Loss | $500 | Stop all trading |
| Consecutive Losses | 5 | Stop all trading |
| Trades/Hour | 10 | Prevent new trades |

**Example**:
```python
# After 5 consecutive losses
circuit_breaker.is_tripped() == True
circuit_breaker.trip_reason() == "consecutive_losses"

# All subsequent signals blocked
handle_signal(buy_signal)  # Blocked
# WARNING Circuit breaker prevents trading: consecutive_losses
```

### 3. Stop Losses

**Dual MA Strategy**:
- Hard stop: -3% from entry price
- Checked on every quote update

**Intraday Spread Strategy**:
- Time-based stop: 60 minutes max hold
- No hard percentage stop (relies on z-score exit)

### 4. End-of-Day Flattening

Both strategies close all positions before market close:

| Strategy | Flatten Time |
|----------|--------------|
| Dual MA | 10 minutes before close (3:50 PM ET) |
| Intraday Spread | 5 minutes before close (3:55 PM ET) |

**Implementation**:
```python
if current_time >= flatten_time:
    for ticker in positions:
        signal = Signal(ticker=ticker, side="flat")
        execution.handle_signal(signal)
```

### 5. Cooldown Periods

**Intraday Spread Only**: 10-minute cooldown between trades
- Prevents overtrading same signal
- Allows spread to stabilize
- Reduces transaction costs

---

## Examples & Scenarios

### Scenario A: Full Trading Day (Dual MA)

**Date**: February 10, 2026 (Monday)
**Strategy**: Dual MA Mean Reversion
**Starting Capital**: $5,000

#### Morning (9:30 AM - 12:00 PM)

**9:30 AM** - Market Open
```
INFO Starting live trading loop for ('TQQQ', 'SQQQ')
INFO Market status: Regular hours=True, Extended hours=False
INFO Circuit breaker initialized: max_daily_loss=500.00, max_consecutive_losses=5
INFO Position reconciliation: no positions found at broker
```

**10:15 AM** - First Signal (TQQQ Oversold)
```
INFO Quote: TQQQ @ $44.20, z_score=-1.52
INFO Submitted buy order: TQQQ x22 @ 44.20 (order_id=100001, reason=entry)
INFO Order 100001 filled: buy TQQQ x22
```

**10:47 AM** - Exit (Mean Reversion)
```
INFO Quote: TQQQ @ $46.80, z_score=+0.12
INFO Submitted sell order: TQQQ x22 @ 46.80 (order_id=100002, reason=exit)
INFO Order 100002 filled: sell TQQQ x22
INFO Trade profit: TQQQ realized_pnl=+$57.20 (consecutive_losses=0, daily_pnl=+$57.20)
```

**11:22 AM** - Second Signal (SQQQ Oversold)
```
INFO Quote: SQQQ @ $12.95, z_score=-1.38
INFO Submitted buy order: SQQQ x77 @ 12.95 (order_id=100003, reason=entry)
INFO Order 100003 filled: buy SQQQ x77
```

**11:58 AM** - Stop Loss Hit
```
WARNING Quote: SQQQ @ $12.56, loss=-3.01%
WARNING Stop loss triggered for SQQQ: -3.0%
INFO Submitted sell order: SQQQ x77 @ 12.56 (order_id=100004, reason=stop_loss)
INFO Order 100004 filled: sell SQQQ x77
INFO Trade loss: SQQQ realized_pnl=-$30.03 (consecutive_losses=1, daily_pnl=+$27.17)
```

#### Afternoon (12:00 PM - 4:00 PM)

**1:15 PM** - Third Signal (TQQQ Oversold Again)
```
INFO Quote: TQQQ @ $45.10, z_score=-1.62
INFO Submitted buy order: TQQQ x22 @ 45.10 (order_id=100005, reason=entry)
INFO Order 100005 filled: buy TQQQ x22
```

**2:03 PM** - Exit (Mean Reversion)
```
INFO Quote: TQQQ @ $46.95, z_score=+0.08
INFO Submitted sell order: TQQQ x22 @ 46.95 (order_id=100006, reason=exit)
INFO Order 100006 filled: sell TQQQ x22
INFO Trade profit: TQQQ realized_pnl=+$40.70 (consecutive_losses=0, daily_pnl=+$67.87)
```

**3:50 PM** - Flatten All Positions (None to close)
```
INFO Flatten time reached, closing all positions
INFO No positions to flatten
```

**4:00 PM** - Market Close
```
INFO Market closed, exiting loop
INFO Daily summary:
  Trades: 3
  Winners: 2 (66.7%)
  Losers: 1 (33.3%)
  Total PnL: +$67.87
  Circuit breaker status: enabled=True, tripped=False
  Max consecutive losses: 1
```

### Scenario B: Circuit Breaker Activation

**Date**: February 11, 2026 (Tuesday)
**Strategy**: Dual MA Mean Reversion
**Starting Daily PnL**: $0

#### Losing Streak

**10:30 AM** - Trade 1: Loss
```
INFO Buy TQQQ x22 @ $45.50
INFO Sell TQQQ x22 @ $44.14 (stop loss)
INFO Trade loss: TQQQ realized_pnl=-$29.92 (consecutive_losses=1, daily_pnl=-$29.92)
```

**11:15 AM** - Trade 2: Loss
```
INFO Buy SQQQ x77 @ $12.80
INFO Sell SQQQ x77 @ $12.42 (stop loss)
INFO Trade loss: SQQQ realized_pnl=-$29.26 (consecutive_losses=2, daily_pnl=-$59.18)
```

**12:45 PM** - Trade 3: Loss
```
INFO Buy TQQQ x22 @ $45.20
INFO Sell TQQQ x22 @ $43.85 (stop loss)
INFO Trade loss: TQQQ realized_pnl=-$29.70 (consecutive_losses=3, daily_pnl=-$88.88)
```

**1:50 PM** - Trade 4: Loss
```
INFO Buy SQQQ x78 @ $12.70
INFO Sell SQQQ x78 @ $12.32 (stop loss)
INFO Trade loss: SQQQ realized_pnl=-$29.64 (consecutive_losses=4, daily_pnl=-$118.52)
```

**2:35 PM** - Trade 5: Loss (Circuit Breaker Trips!)
```
INFO Buy TQQQ x22 @ $45.80
INFO Sell TQQQ x22 @ $44.43 (stop loss)
INFO Trade loss: TQQQ realized_pnl=-$30.14 (consecutive_losses=5, daily_pnl=-$148.66)

ERROR CIRCUIT BREAKER TRIPPED: Too many consecutive losses (count=5, limit=5)
CRITICAL CIRCUIT BREAKER ACTIVATED: consecutive_losses - Trading halted!
```

**2:36 PM** - Subsequent Signal Blocked
```
INFO Quote: SQQQ @ $12.60, z_score=-1.55 (would be entry signal)
WARNING Circuit breaker prevents trading: consecutive_losses (signal=buy SQQQ)
```

**3:50 PM** - Flatten Time (Nothing to Flatten)
```
INFO Flatten time reached, closing all positions
INFO No positions to flatten (circuit breaker active)
```

**4:00 PM** - End of Day
```
INFO Market closed, exiting loop
INFO Daily summary:
  Trades: 5
  Winners: 0 (0%)
  Losers: 5 (100%)
  Total PnL: -$148.66
  Circuit breaker status: enabled=True, tripped=True, reason=consecutive_losses
  Max consecutive losses: 5

WARNING Circuit breaker remains ACTIVE - manual reset required for next session
```

**Next Day Reset**:
```python
# Manual reset required at start of new session
execution.reset_circuit_breaker()
# INFO Resetting circuit breaker for new trading day (previous daily_pnl=-148.66, consecutive_losses=5)
# INFO Circuit breaker reset for new trading session
```

### Scenario C: Intraday Spread High-Frequency Trading

**Date**: February 12, 2026 (Wednesday)
**Strategy**: Intraday Pair Spread
**Timeframe**: 9:30 AM - 11:00 AM (90 minutes)

#### Rapid Trading Sequence

**10:05 AM** - Signal 1: Buy TQQQ (Z < -2.0)
```
INFO Log spread z_score=-2.15, entry signal
INFO Buy TQQQ x22 @ $45.30 (order_id=200001)
```

**10:18 AM** - Exit 1: Z-score reverted (13 min hold)
```
INFO Log spread z_score=-0.48, exit signal
INFO Sell TQQQ x22 @ $45.65 (order_id=200002)
INFO Trade profit: +$7.70, hold_minutes=13
INFO Cooldown active until 10:28 AM
```

**10:28 AM** - Cooldown Expires
```
INFO Cooldown period ended, monitoring for new signals
```

**10:31 AM** - Signal 2: Buy SQQQ (Z > +2.0)
```
INFO Log spread z_score=+2.08, entry signal
INFO Buy SQQQ x78 @ $12.75 (order_id=200003)
```

**10:52 AM** - Exit 2: Z-score reverted (21 min hold)
```
INFO Log spread z_score=+0.42, exit signal
INFO Sell SQQQ x78 @ $12.87 (order_id=200004)
INFO Trade profit: +$9.36, hold_minutes=21
INFO Cooldown active until 11:02 AM
```

**11:02 AM** - Cooldown Expires
```
INFO Cooldown period ended, monitoring for new signals
```

**Summary (9:30-11:00 AM)**:
```
Trades: 2
Win Rate: 100%
Total PnL: +$17.06
Average Hold Time: 17 minutes
```

---

## Performance Considerations

### Expected Returns

| Strategy | Daily Target | Win Rate | Avg Trade | Trades/Day |
|----------|--------------|----------|-----------|------------|
| Dual MA | 1-3% | 55-60% | +$40 | 2-4 |
| Intraday Spread | 2-5% | 50-55% | +$15 | 5-15 |

**Note**: These are approximate targets. Actual performance varies significantly based on market conditions.

### Transaction Costs

**Schwab Commission**: $0 (commission-free)
**Estimated Slippage**: $0.01-0.05 per share
**Impact on Returns**: -0.1% to -0.5% per trade

### Market Conditions

**Favorable Conditions**:
- High volatility (VIX > 20)
- Trending markets with pullbacks
- Clear regime (bullish or bearish)

**Unfavorable Conditions**:
- Low volatility (VIX < 15)
- Choppy, sideways markets
- Regime uncertainty

### Risk Metrics

**Maximum Daily Drawdown**: -$500 (circuit breaker)
**Maximum Position Risk**: $1,000 per ticker
**Sharpe Ratio Target**: > 1.5
**Max Consecutive Losses**: 5 (circuit breaker)

---

## Configuration Guide

### Choosing a Strategy

**Use Dual MA Mean Reversion if**:
- You prefer 2-4 trades per day
- You want longer hold times (30-90 min)
- Market shows clear trends
- You have historical price data

**Use Intraday Pair Spread if**:
- You want 5-15 trades per day
- You prefer rapid in/out (15-30 min)
- You have 1-minute data feed
- You want market-neutral exposure

### Adjusting Parameters

#### Conservative Settings (Lower Risk)
```python
# Dual MA
entry_zscore: float = 1.5      # More selective (wider deviation required)
stop_loss_pct: float = 0.02    # Tighter stop loss (2%)

# Intraday Spread
entry_zscore: float = 2.5      # More selective
max_hold_minutes: int = 45     # Shorter holds

# Circuit Breaker
max_daily_loss: float = 300.0  # Lower limit
max_consecutive_losses: int = 3  # Fewer chances
```

#### Aggressive Settings (Higher Risk)
```python
# Dual MA
entry_zscore: float = 0.8      # Less selective
stop_loss_pct: float = 0.05    # Wider stop (5%)

# Intraday Spread
entry_zscore: float = 1.5      # Less selective
max_hold_minutes: int = 90     # Longer holds

# Circuit Breaker
max_daily_loss: float = 1000.0  # Higher limit
max_consecutive_losses: int = 7  # More chances
```

### Position Sizing

Adjust based on account size:

**Small Account ($5,000)**:
```python
max_position_size = 500.0      # $500 per position
max_total_exposure = 750.0     # $750 total
```

**Medium Account ($25,000)**:
```python
max_position_size = 2500.0     # $2,500 per position
max_total_exposure = 5000.0    # $5,000 total
```

**Large Account ($100,000)**:
```python
max_position_size = 10000.0    # $10,000 per position
max_total_exposure = 20000.0   # $20,000 total
```

---

## Frequently Asked Questions

### Q: Why leveraged ETFs?
**A**: High volatility creates more mean reversion opportunities. 3x leverage amplifies small price movements, making statistical edges more profitable.

### Q: Why trade both TQQQ and SQQQ?
**A**: They're inverse pairs tracking the same underlying (Nasdaq). Dual MA trades whichever is in the favorable regime. Intraday Spread exploits their relative mispricing.

### Q: What's the optimal holding period?
**A**: Dual MA: 30-90 minutes. Intraday Spread: 15-30 minutes. Longer holds increase risk of reversal.

### Q: How much capital needed?
**A**: Minimum $5,000 recommended. Below this, position sizing becomes too small to be effective after accounting for minimums.

### Q: Can I run both strategies simultaneously?
**A**: Yes, but watch total exposure limits. Each strategy can hold $1,500, so total could reach $3,000 if both active.

### Q: What happens if I lose internet connection?
**A**: Bot stops processing. Existing positions remain open at broker. Restart required, position reconciliation will sync state.

### Q: Do I need tick-by-tick data?
**A**: No. Dual MA uses daily + periodic quotes. Intraday Spread uses 1-minute bars (not ticks).

### Q: What's the learning curve?
**A**: Basic setup: 1 hour. Understanding strategies: 2-4 hours. Comfortable operation: 1-2 weeks of paper trading.

---

**End of Strategy Guide**
