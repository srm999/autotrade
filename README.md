# autotrade

> Automated Robinhood trading bot focused on TQQQ/SQQQ trend regime and mean reversion.

## ⚠️ Disclaimers
- Automating trades may violate Robinhood's terms of service. Review and accept full responsibility before using this software.
- This repository is for educational purposes. Real capital use is at your own risk.
- Keep credentials secret. Never commit or share them.

## Project layout
```
autotrade/
  broker/          # Robinhood client wrapper
  data/            # Market data helpers & local history cache
  strategy/        # Strategy abstractions & dual MA mean-reversion strategy
  trading/         # Execution and trading loop orchestration
main.py            # CLI entry point
requirements.txt   # Python dependencies
```

## Getting started
1. **Create a virtual environment** (Python 3.11 recommended):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
2. **Export Robinhood credentials** (consider using a `.env` loader instead of plain export):
   ```bash
   export ROBINHOOD_USERNAME="your_email"
   export ROBINHOOD_PASSWORD="your_password"
   # Optional if your account uses MFA / device token
   export ROBINHOOD_MFA_CODE="123456"
   export ROBINHOOD_DEVICE_TOKEN="device-token"
   ```
3. **Run in paper mode first** (logs trades instead of placing them):
   ```bash
   python main.py --dry-run --log-level=DEBUG
   ```
4. **Go live carefully** once you have validated behaviour:
   ```bash
   python main.py --log-level=INFO
   ```

## Strategy customization
- Default deployment trades only `TQQQ` and `SQQQ`, using a 50/250-day moving-average regime filter with z-score mean reversion entries.
- Tweak exposure limits or indicator parameters in `BotConfig.default()` inside `autotrade/config.py`.
- Extend functionality by implementing additional classes that satisfy the `Strategy` protocol in `autotrade/strategy/base.py`, then instantiate them in `autotrade/trading/loop.py`.

## Historical data cache
- The bot persists roughly one year of daily candles per ticker under `data/history/<TICKER>.csv` using `HistoryStore`.
- On the first run it backfills the last year from Robinhood; subsequent sessions append new sessions, keeping calculations fast and reproducible.
- Delete the CSV if you need a fresh pull; it will be regenerated automatically.

## Next steps
- Backtest the regime/mean-reversion logic and capture baseline performance metrics.
- Add richer risk controls (daily loss caps, number of trades per session) and execution throttling.
- Persist fills/decisions for monitoring and analytics.
- Layer additional strategies (e.g., volatility breakout, options hedges) using the same infrastructure.
