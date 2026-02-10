"""
Backtest runner for testing strategies on historical data.

Usage:
    # Install dependencies first
    pip install -r requirements.txt

    # Run backtest
    python scripts/backtest_runner.py --strategy trend_following --start 2020-01-01 --end 2024-12-31

This script:
1. Loads historical data using yfinance
2. Runs strategy backtest with realistic costs
3. Calculates performance metrics
4. Displays results

IMPORTANT: Always backtest before live trading!
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

_LOG = logging.getLogger(__name__)


def load_historical_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Load historical daily data using yfinance.

    Args:
        ticker: Stock symbol (e.g., "SPY", "QQQ")
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        DataFrame with OHLCV data and proper column names
    """
    try:
        import yfinance as yf
    except ImportError:
        _LOG.error(
            "yfinance not installed. Run: pip install yfinance\n"
            "Or: pip install -r requirements.txt"
        )
        raise

    _LOG.info("Loading %s data from %s to %s...", ticker, start_date, end_date)

    # Download data from yfinance
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)

    if data.empty:
        _LOG.warning("No data returned for %s", ticker)
        return pd.DataFrame()

    # Rename columns to match our format
    data = data.rename(columns={
        'Open': 'open_price',
        'High': 'high_price',
        'Low': 'low_price',
        'Close': 'close_price',
        'Volume': 'volume'
    })

    # Add date column
    data['date'] = data.index
    data = data.reset_index(drop=True)

    _LOG.info("Loaded %d days of data for %s", len(data), ticker)

    return data


def calculate_atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range (ATR) for volatility-based position sizing.

    Args:
        highs: High prices
        lows: Low prices
        closes: Close prices
        period: ATR period (default 14)

    Returns:
        Series of ATR values
    """
    prev_closes = closes.shift(1)

    tr1 = highs - lows
    tr2 = (highs - prev_closes).abs()
    tr3 = (lows - prev_closes).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()

    return atr


def run_backtest(
    strategy_name: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 10_000.0,
    show_trades: bool = False
) -> None:
    """
    Run backtest for a strategy over a date range.

    Args:
        strategy_name: Name of strategy to test
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        initial_capital: Starting capital
        show_trades: If True, print all trades
    """
    _LOG.info("=" * 80)
    _LOG.info("BACKTEST: %s", strategy_name.upper())
    _LOG.info("Period: %s to %s", start_date, end_date)
    _LOG.info("Initial Capital: $%.2f", initial_capital)
    _LOG.info("=" * 80)

    # Import here to avoid circular imports
    from autotrade.backtest import BacktestEngine, BacktestConfig
    from autotrade.config import BotConfig, TrendFollowingParams

    # Configure backtest with realistic transaction costs for Schwab
    backtest_config = BacktestConfig(
        initial_capital=initial_capital,
        commission_pct=0.0,  # Schwab has $0 commissions
        commission_fixed=0.0,
        slippage_pct=0.01,  # 1 basis point (0.01%) - Schwab spreads are tight
        sec_fee_rate=0.0000278,  # SEC fee per dollar sold
        taf_fee_per_share=0.000166,  # TAF fee (capped at $7.27)
        max_positions=5,
        position_size_pct=25.0  # 25% max per position
    )

    # Create backtest engine
    engine = BacktestEngine(backtest_config)

    # Load strategy configuration
    bot_config = BotConfig.default(strategy=strategy_name, capital=initial_capital)

    _LOG.info("\nStrategy Configuration:")
    _LOG.info("  Tickers: %s", bot_config.strategy.tickers)
    _LOG.info("  Max position size: $%.2f", bot_config.strategy.max_position_size)
    _LOG.info("  Max total exposure: $%.2f", bot_config.strategy.max_total_exposure)
    _LOG.info("  Circuit breaker max daily loss: $%.2f", bot_config.circuit_breaker.max_daily_loss)

    # Load historical data for all tickers
    _LOG.info("\nLoading historical data...")
    ticker_data = {}

    for ticker in bot_config.strategy.tickers:
        data = load_historical_data(ticker, start_date, end_date)
        if not data.empty:
            ticker_data[ticker] = data
        else:
            _LOG.warning("Skipping %s due to missing data", ticker)

    if not ticker_data:
        _LOG.error("No data loaded for any tickers. Exiting.")
        return

    _LOG.info("Loaded data for %d tickers", len(ticker_data))

    # Get strategy parameters
    params = bot_config.strategy.params
    if not isinstance(params, TrendFollowingParams):
        _LOG.error("Strategy params must be TrendFollowingParams")
        return

    # Find common date range across all tickers
    all_dates = set()
    for data in ticker_data.values():
        all_dates.update(data['date'].tolist())

    trading_dates = sorted(list(all_dates))
    _LOG.info("\nBacktest period: %d trading days", len(trading_dates))

    # Pre-calculate indicators for all tickers
    _LOG.info("\nCalculating indicators...")
    indicators = {}

    for ticker, data in ticker_data.items():
        data = data.set_index('date').sort_index()

        # Ensure we get 1D Series (squeeze if multi-column)
        closes = data['close_price'].squeeze().astype(float)
        highs = data['high_price'].squeeze().astype(float)
        lows = data['low_price'].squeeze().astype(float)

        # Calculate moving averages
        sma_10 = closes.rolling(window=params.sma_exit).mean()
        sma_50 = closes.rolling(window=params.sma_fast).mean()
        sma_200 = closes.rolling(window=params.sma_slow).mean()

        # Calculate 20-day high
        high_20 = highs.rolling(window=params.breakout_period).max()

        # Calculate ATR
        atr = calculate_atr(highs, lows, closes, period=params.atr_period)

        indicators[ticker] = pd.DataFrame({
            'close': closes,
            'high': highs,
            'low': lows,
            'sma_10': sma_10,
            'sma_50': sma_50,
            'sma_200': sma_200,
            'high_20': high_20,
            'atr': atr,
        })

        _LOG.info("  %s: SMA-50=%.2f, SMA-200=%.2f, ATR=%.2f",
                  ticker,
                  sma_50.iloc[-1] if len(sma_50) > 0 else 0,
                  sma_200.iloc[-1] if len(sma_200) > 0 else 0,
                  atr.iloc[-1] if len(atr) > 0 else 0)

    # Track positions for signal generation
    positions = {ticker: None for ticker in ticker_data.keys()}  # None or entry_date
    entry_prices = {ticker: None for ticker in ticker_data.keys()}
    highest_prices = {ticker: None for ticker in ticker_data.keys()}

    # Backtest loop
    _LOG.info("\nRunning backtest...")
    trade_count = 0

    for date in trading_dates:
        current_prices = {}

        # Get current price for all tickers
        for ticker in ticker_data.keys():
            if ticker not in indicators:
                continue

            ind = indicators[ticker]
            if date not in ind.index:
                continue

            current_prices[ticker] = ind.loc[date, 'close']

        # Update equity curve
        engine.update_equity(date, current_prices)
        engine.calculate_daily_return()

        # Generate signals for each ticker
        for ticker in ticker_data.keys():
            if ticker not in indicators:
                continue

            ind = indicators[ticker]
            if date not in ind.index:
                continue

            row = ind.loc[date]
            price = row['close']
            sma_10 = row['sma_10']
            sma_50 = row['sma_50']
            sma_200 = row['sma_200']
            high_20 = row['high_20']
            atr = row['atr']

            # Skip if indicators not ready
            if pd.isna(sma_200) or pd.isna(high_20) or pd.isna(atr):
                continue

            # Check for signals
            in_position = positions[ticker] is not None

            if in_position:
                # Update trailing high
                if highest_prices[ticker] is None or price > highest_prices[ticker]:
                    highest_prices[ticker] = price

                # Check exit conditions - SLOWER EXITS to hold trends longer
                should_exit = False
                exit_reason = None

                # Exit 1: Price crosses below 50 MA (trend reversal)
                # Changed from 10 MA to 50 MA to stay in trends longer
                if not pd.isna(sma_50) and price < sma_50:
                    should_exit = True
                    exit_reason = "trend_reversal"

                # Exit 2: ATR-based stop loss (wider stops)
                # Increased from 2x to 2.5x ATR for less whipsaw
                entry_price = entry_prices[ticker]
                if not should_exit and entry_price and atr:
                    stop_price = entry_price - (atr * 2.5)  # Wider stop
                    if price < stop_price:
                        should_exit = True
                        exit_reason = "stop_loss"

                # Exit 3: Time stop (increased to hold winners longer)
                # Only exit on time if losing money
                entry_date = positions[ticker]
                if not should_exit and entry_date:
                    days_held = (date - entry_date).days
                    if days_held >= params.max_hold_days:
                        # Only exit on time stop if underwater
                        if entry_price and price < entry_price:
                            should_exit = True
                            exit_reason = "time_stop"

                if should_exit:
                    # Sell position
                    position = engine._positions.get(ticker)
                    if position and position.quantity > 0:
                        trade = engine.execute_trade(
                            date, ticker, 'sell', position.quantity, price
                        )

                        if trade:
                            pnl = (price - entry_price) * position.quantity if entry_price else 0
                            pnl_pct = ((price - entry_price) / entry_price * 100) if entry_price else 0

                            trade_count += 1

                            if show_trades:
                                _LOG.info(
                                    "SELL %s: %d shares @ $%.2f (entry=$%.2f, pnl=$%.2f, pnl_pct=%.2f%%, reason=%s)",
                                    ticker, trade.quantity, price, entry_price, pnl, pnl_pct, exit_reason
                                )

                        # Reset position tracking
                        positions[ticker] = None
                        entry_prices[ticker] = None
                        highest_prices[ticker] = None

            else:
                # Check entry conditions - MORE RESTRICTIVE to reduce overtrading
                # 1. Price > 50 MA (in uptrend)
                if price <= sma_50:
                    continue

                # 2. 50 MA > 200 MA (long-term uptrend)
                if sma_50 <= sma_200:
                    continue

                # 3. Strong momentum: Price within 0.5% of 20-day high (STRICTER)
                # This reduces false signals and overtrading
                if price < high_20 * 0.995:
                    continue

                # 4. Additional filter: Price > 200 MA (very strong trend only)
                if price <= sma_200:
                    continue

                # Check if we can open new position
                if not engine.can_open_position():
                    continue

                # Calculate position size (2% risk per trade)
                quantity = engine.calculate_position_size(
                    ticker=ticker,
                    price=price,
                    risk_pct=2.0,
                    atr=atr,
                    atr_multiplier=params.atr_stop_multiplier
                )

                if quantity > 0:
                    trade = engine.execute_trade(date, ticker, 'buy', quantity, price)

                    if trade:
                        positions[ticker] = date
                        entry_prices[ticker] = price
                        highest_prices[ticker] = price
                        trade_count += 1

                        if show_trades:
                            _LOG.info(
                                "BUY %s: %d shares @ $%.2f (sma50=%.2f, sma200=%.2f, high20=%.2f, atr=%.2f)",
                                ticker, quantity, price, sma_50, sma_200, high_20, atr
                            )

    # Get results
    results = engine.get_results()
    metrics = results.metrics

    # Display results
    _LOG.info("\n" + "=" * 80)
    _LOG.info("BACKTEST RESULTS")
    _LOG.info("=" * 80)

    if metrics:
        _LOG.info("\n%s", metrics)

        _LOG.info("\nTrade Summary:")
        _LOG.info("  Total Trades: %d", len(results.trades))
        _LOG.info("  Transaction Costs: $%.2f", sum(t.total_cost for t in results.trades))
        _LOG.info("  Avg Cost per Trade: $%.2f",
                  sum(t.total_cost for t in results.trades) / len(results.trades) if results.trades else 0)

        if not results.equity_curve.empty:
            final_value = results.equity_curve.iloc[-1]
            total_return = ((final_value - initial_capital) / initial_capital) * 100

            _LOG.info("\nPortfolio Value:")
            _LOG.info("  Starting Capital: $%.2f", initial_capital)
            _LOG.info("  Ending Capital: $%.2f", final_value)
            _LOG.info("  Total Return: $%.2f (%.2f%%)", final_value - initial_capital, total_return)

        # Quality check
        _LOG.info("\n" + "=" * 80)
        _LOG.info("QUALITY CHECK")
        _LOG.info("=" * 80)

        checks = []
        checks.append(("Sharpe Ratio > 1.0", metrics.sharpe_ratio >= 1.0, f"{metrics.sharpe_ratio:.2f}"))
        checks.append(("Max Drawdown < 25%", metrics.max_drawdown <= 25.0, f"{metrics.max_drawdown:.2f}%"))
        checks.append(("Win Rate > 40%", metrics.win_rate >= 0.40, f"{metrics.win_rate * 100:.1f}%"))
        checks.append(("Profit Factor > 2.0", metrics.profit_factor >= 2.0, f"{metrics.profit_factor:.2f}"))

        for check_name, passed, value in checks:
            status = "✅ PASS" if passed else "❌ FAIL"
            _LOG.info("  %s: %s (%s)", check_name, status, value)

        all_passed = all(c[1] for c in checks)

        _LOG.info("\n" + "=" * 80)
        if all_passed:
            _LOG.info("✅ STRATEGY MEETS MINIMUM STANDARDS")
            _LOG.info("Next step: Test on different time periods and market conditions")
        else:
            _LOG.info("❌ STRATEGY NEEDS IMPROVEMENT")
            _LOG.info("Consider: Adjusting parameters, testing different tickers, or trying a different strategy")
        _LOG.info("=" * 80)

    else:
        _LOG.error("No metrics calculated")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backtest trading strategies with realistic costs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic backtest (2020-2024)
  python scripts/backtest_runner.py --strategy trend_following

  # Test specific period
  python scripts/backtest_runner.py --start 2022-01-01 --end 2022-12-31

  # Show all trades
  python scripts/backtest_runner.py --show-trades

  # Different capital
  python scripts/backtest_runner.py --capital 50000
        """
    )

    parser.add_argument(
        "--strategy",
        default="trend_following",
        choices=["trend_following"],
        help="Strategy to backtest (default: trend_following)"
    )

    parser.add_argument(
        "--start",
        default="2020-01-01",
        help="Start date YYYY-MM-DD (default: 2020-01-01)"
    )

    parser.add_argument(
        "--end",
        default="2024-12-31",
        help="End date YYYY-MM-DD (default: 2024-12-31)"
    )

    parser.add_argument(
        "--capital",
        type=float,
        default=10_000.0,
        help="Initial capital (default: $10,000)"
    )

    parser.add_argument(
        "--show-trades",
        action="store_true",
        help="Show all individual trades"
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Run backtest
    try:
        run_backtest(
            strategy_name=args.strategy,
            start_date=args.start,
            end_date=args.end,
            initial_capital=args.capital,
            show_trades=args.show_trades
        )
    except Exception as exc:
        _LOG.exception("Backtest failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
