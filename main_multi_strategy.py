"""Multi-strategy trading bot - continuous operation during market hours.

This is the production trading bot that:
1. Runs continuously during market hours
2. Detects market regime every hour
3. Activates appropriate strategies based on regime
4. Scans watchlists for setups
5. Generates signals and executes trades
6. Manages risk across all strategies

Usage:
    python main_multi_strategy.py [--dry-run] [--capital AMOUNT]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, time as dt_time
from pathlib import Path

import pandas as pd

# Add autotrade to path
sys.path.insert(0, str(Path(__file__).parent))

from autotrade.analysis.market_regime import MarketRegimeDetector
from autotrade.broker.schwab_client import SchwabClient
from autotrade.config import BotConfig, MeanReversionParams, MomentumBreakoutParams
from autotrade.scanner.stock_screener import StockScreener, ScreenerCriteria
from autotrade.scanner.watchlist import WatchlistManager
from autotrade.strategy.mean_reversion import MeanReversionStrategy
from autotrade.strategy.momentum_breakout import MomentumBreakoutStrategy
from autotrade.strategy.strategy_manager import StrategyManager
# from autotrade.strategy.trend_following import TrendFollowingStrategy  # Uses old interface
from autotrade.trading.circuit_breaker import CircuitBreaker
from autotrade.trading.execution import TradeExecutor
from autotrade.trading.reporting import PerformanceReporter
from autotrade.utils.market_hours import is_market_open, get_market_status

_LOG = logging.getLogger(__name__)


class MultiStrategyBot:
    """Multi-strategy trading bot with continuous operation."""

    def __init__(
        self,
        config: BotConfig,
        dry_run: bool = True,
    ):
        """
        Initialize multi-strategy bot.

        Args:
            config: Bot configuration
            dry_run: If True, simulate trades without executing
        """
        self.config = config
        self.dry_run = dry_run

        # Initialize components
        self.broker = SchwabClient() if not dry_run else None
        self.strategy_manager = StrategyManager()
        self.regime_detector = MarketRegimeDetector()
        self.watchlist_manager = WatchlistManager()
        self.screener = StockScreener()
        self.circuit_breaker = CircuitBreaker(
            max_daily_loss=config.circuit_breaker.max_daily_loss,
            max_consecutive_losses=config.circuit_breaker.max_consecutive_losses,
            max_trades_per_hour=config.circuit_breaker.max_trades_per_hour,
            enabled=config.circuit_breaker.enabled,
        )
        self.executor = TradeExecutor(
            broker=self.broker,
            circuit_breaker=self.circuit_breaker,
            dry_run=dry_run,
        )
        self.reporter = PerformanceReporter(reports_dir="reports")

        # State
        self._last_regime_check = None
        self._last_scan_time = None
        self._last_report_date = None
        self._positions: dict[str, dict] = {}  # ticker -> position info

        # Initialize strategies
        self._initialize_strategies()

        # Initialize watchlists
        self._initialize_watchlists()

        _LOG.info("Multi-strategy bot initialized (dry_run=%s)", dry_run)

    def _initialize_strategies(self) -> None:
        """Register all available strategies."""
        # Mean reversion (for ranging markets)
        mean_reversion_strategy = MeanReversionStrategy(MeanReversionParams())
        self.strategy_manager.register_strategy(mean_reversion_strategy, auto_activate=True)

        # Momentum breakout (for strong trends)
        momentum_strategy = MomentumBreakoutStrategy(MomentumBreakoutParams())
        self.strategy_manager.register_strategy(momentum_strategy, auto_activate=True)

        # NOTE: TrendFollowingStrategy uses old interface - not compatible with multi-strategy system yet
        # TODO: Create new version of trend following strategy with multi-strategy interface

        _LOG.info("Registered 2 strategies (mean reversion, momentum breakout)")

    def _initialize_watchlists(self) -> None:
        """Initialize watchlists."""
        # Create default watchlists if they don't exist
        if not self.watchlist_manager.get_watchlist("primary"):
            self.watchlist_manager.create_watchlist(
                name="primary",
                tickers=["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "TSLA"],
                description="Primary trading universe",
            )

        if not self.watchlist_manager.get_watchlist("screener_momentum"):
            self.watchlist_manager.create_watchlist(
                name="screener_momentum",
                tickers=[],
                description="High momentum stocks from screener",
                is_dynamic=True,
            )

        _LOG.info("Initialized watchlists")

    def run(self) -> None:
        """Run the main trading loop."""
        _LOG.info("Starting multi-strategy trading bot...")
        _LOG.info("Market hours: %s - %s", self.config.trading_window.market_open, self.config.trading_window.market_close)

        try:
            while True:
                # Check if market is open
                if not is_market_open():
                    status = get_market_status()
                    _LOG.info("Market closed - %s. Sleeping...", status)
                    time.sleep(300)  # Check every 5 minutes
                    continue

                # Market is open - run trading cycle
                try:
                    self._trading_cycle()
                except Exception as e:
                    _LOG.error("Error in trading cycle: %s", e, exc_info=True)
                    self.reporter.record_error(e, context="trading_cycle")

                # Sleep before next cycle
                time.sleep(self.config.polling_interval_seconds)

        except KeyboardInterrupt:
            _LOG.info("Shutting down bot...")
            self._shutdown()

    def _trading_cycle(self) -> None:
        """Execute one trading cycle."""
        now = datetime.now()

        # Check if we should generate end-of-day report
        if self._should_generate_daily_report():
            self._generate_daily_report()
            self._last_report_date = now.date()

        # 1. Update market regime (every hour)
        if self._should_update_regime():
            self._update_market_regime()

        # 2. Run screener (every 30 minutes)
        if self._should_run_screener():
            self._run_screener()

        # 3. Get combined watchlist
        watchlist_tickers = self.watchlist_manager.get_combined_tickers()
        _LOG.info("Monitoring %d tickers from watchlists", len(watchlist_tickers))

        # 4. Monitor positions and check exits
        self._monitor_positions()

        # 5. Scan for entry signals
        self._scan_for_entries(watchlist_tickers)

        # 6. Log status
        self._log_status()

    def _should_update_regime(self) -> bool:
        """Check if we should update market regime."""
        if self._last_regime_check is None:
            return True

        # Update every hour
        elapsed = (datetime.now() - self._last_regime_check).total_seconds()
        return elapsed >= 3600

    def _update_market_regime(self) -> None:
        """Update market regime and activate compatible strategies."""
        _LOG.info("Updating market regime...")

        try:
            # Fetch SPY data for regime detection
            spy_data = self._fetch_price_data("SPY", days=250)
            if spy_data is None or len(spy_data) < 200:
                _LOG.warning("Insufficient data for regime detection")
                return

            # Detect regime
            regime = self.regime_detector.detect_regime(
                prices=spy_data["close"],
                vix=None,  # TODO: Fetch VIX if needed
            )

            # Update strategies
            self.strategy_manager.update_regime(regime)

            self._last_regime_check = datetime.now()

            # Log active strategies
            active = self.strategy_manager.get_active_strategies()
            _LOG.info("Active strategies: %s", ", ".join(active))

            # Record regime change
            self.reporter.record_regime_change(str(regime), active)

        except Exception as e:
            _LOG.error("Error updating market regime: %s", e)

    def _should_run_screener(self) -> bool:
        """Check if we should run stock screener."""
        if self._last_scan_time is None:
            return True

        # Run every 30 minutes
        elapsed = (datetime.now() - self._last_scan_time).total_seconds()
        return elapsed >= 1800

    def _should_generate_daily_report(self) -> bool:
        """Check if we should generate the daily report.

        Generate report once per day after market close (4:00 PM ET).
        """
        now = datetime.now()

        # Check if already generated today
        if self._last_report_date == now.date():
            return False

        # Check if it's after market close (4:00 PM ET)
        from autotrade.utils.market_hours import is_market_open
        if is_market_open():
            return False

        # Check if it's after 4:00 PM local time
        if now.hour >= 16:
            return True

        return False

    def _run_screener(self) -> None:
        """Run stock screener and update dynamic watchlists."""
        _LOG.info("Running stock screener...")

        try:
            # Get universe to scan
            universe = self.watchlist_manager.get_default_universe()

            # Scan universe
            results = self.screener.scan_universe(
                universe=universe,
                data_fetcher=lambda ticker: self._fetch_price_data(ticker, days=50),
            )

            # Update dynamic watchlist with top momentum stocks
            if results:
                top_momentum = [r.ticker for r in results[:10]]
                self.watchlist_manager.update_dynamic_watchlist(
                    "screener_momentum",
                    top_momentum,
                )
                _LOG.info("Updated screener watchlist with %d tickers", len(top_momentum))

            self._last_scan_time = datetime.now()

        except Exception as e:
            _LOG.error("Error running screener: %s", e)

    def _monitor_positions(self) -> None:
        """Monitor existing positions and check exit conditions."""
        if not self._positions:
            return

        _LOG.debug("Monitoring %d positions", len(self._positions))

        for ticker, position in list(self._positions.items()):
            try:
                # Fetch current price
                current_data = self._fetch_price_data(ticker, days=1)
                if current_data is None or len(current_data) == 0:
                    continue

                current_price = current_data["close"].iloc[-1]

                # Calculate days held
                entry_date = position["entry_date"]
                days_held = (datetime.now() - entry_date).days

                # Check exit conditions
                should_exit, exit_reason = self.strategy_manager.check_exit_conditions(
                    ticker=ticker,
                    strategy_name=position["strategy"],
                    entry_price=position["entry_price"],
                    current_price=current_price,
                    direction=position["direction"],
                    days_held=days_held,
                )

                if should_exit:
                    _LOG.info(
                        "%s: Exit signal (%s) - Price=%.2f, Entry=%.2f, Days=%d",
                        ticker,
                        exit_reason,
                        current_price,
                        position["entry_price"],
                        days_held,
                    )

                    # Execute exit
                    quantity = position["quantity"]
                    action = "sell" if position["direction"] == "long" else "buy"

                    # Calculate P&L
                    if position["direction"] == "long":
                        pnl = (current_price - position["entry_price"]) * quantity
                    else:
                        pnl = (position["entry_price"] - current_price) * quantity

                    if self.executor.execute_trade(
                        ticker=ticker,
                        action=action,
                        quantity=quantity,
                        price=current_price,
                    ):
                        # Record exit trade with P&L
                        self.reporter.record_trade(
                            ticker=ticker,
                            action=action,
                            quantity=quantity,
                            price=current_price,
                            strategy=position["strategy"],
                            pnl=pnl,
                        )

                        # Remove from positions
                        del self._positions[ticker]
                        _LOG.info("%s: Position closed - P&L: %+.2f", ticker, pnl)

            except Exception as e:
                _LOG.error("Error monitoring position for %s: %s", ticker, e)

    def _scan_for_entries(self, tickers: set[str]) -> None:
        """Scan for entry signals across watchlist."""
        for ticker in tickers:
            # Skip if already have position
            if ticker in self._positions:
                continue

            try:
                # Fetch price data
                data = self._fetch_price_data(ticker, days=250)
                if data is None or len(data) < 50:
                    continue

                # Convert to MarketData format
                from autotrade.data.market import MarketData

                market_data = MarketData(
                    ticker=ticker,
                    date=data.index.tolist(),
                    open_price=data["open"].tolist(),
                    high_price=data["high"].tolist(),
                    low_price=data["low"].tolist(),
                    close_price=data["close"].tolist(),
                    volume=data["volume"].tolist(),
                )

                # Generate signals from all active strategies
                signals = self.strategy_manager.generate_signals(ticker, market_data)

                # Execute strongest signal
                if signals:
                    # Sort by confidence
                    signals.sort(key=lambda s: s.confidence, reverse=True)
                    best_signal = signals[0]

                    strategy_name = best_signal.metadata.get("strategy", "unknown")

                    _LOG.info(
                        "%s: Signal from %s (confidence=%.2f)",
                        ticker,
                        strategy_name,
                        best_signal.confidence,
                    )

                    # Calculate position size (simplified - 2% risk)
                    # TODO: Use proper position sizing based on ATR
                    position_value = self.config.strategy.max_position_size
                    quantity = int(position_value / best_signal.price)

                    if quantity > 0:
                        # Execute trade
                        action = "buy" if best_signal.direction == "long" else "sell"
                        executed = self.executor.execute_trade(
                            ticker=ticker,
                            action=action,
                            quantity=quantity,
                            price=best_signal.price,
                        )

                        # Record signal
                        self.reporter.record_signal(
                            ticker=ticker,
                            signal_type="entry",
                            strategy=strategy_name,
                            confidence=best_signal.confidence,
                            executed=executed,
                        )

                        if executed:
                            # Track position
                            self._positions[ticker] = {
                                "strategy": strategy_name,
                                "entry_price": best_signal.price,
                                "entry_date": datetime.now(),
                                "quantity": quantity,
                                "direction": best_signal.direction,
                            }
                            _LOG.info(
                                "%s: Position opened (%d shares @ %.2f)",
                                ticker,
                                quantity,
                                best_signal.price,
                            )

                            # Record trade
                            self.reporter.record_trade(
                                ticker=ticker,
                                action=action,
                                quantity=quantity,
                                price=best_signal.price,
                                strategy=strategy_name,
                                pnl=None,  # Entry trade, no P&L yet
                            )

            except Exception as e:
                _LOG.error("Error scanning %s: %s", ticker, e)

    def _fetch_price_data(self, ticker: str, days: int = 250) -> pd.DataFrame | None:
        """
        Fetch historical price data.

        Args:
            ticker: Stock ticker
            days: Number of days of history

        Returns:
            DataFrame with OHLCV data
        """
        try:
            import yfinance as yf

            # Fetch data
            data = yf.download(ticker, period=f"{days}d", progress=False)

            if len(data) == 0:
                return None

            # Rename columns to lowercase
            data.columns = [c.lower() for c in data.columns]

            return data

        except Exception as e:
            _LOG.warning("Error fetching data for %s: %s", ticker, e)
            return None

    def _log_status(self) -> None:
        """Log current bot status."""
        regime = self.strategy_manager.current_regime
        active_strategies = self.strategy_manager.get_active_strategies()
        position_count = len(self._positions)

        _LOG.info(
            "Status: Regime=%s, Active Strategies=%d, Positions=%d",
            regime if regime else "Unknown",
            len(active_strategies),
            position_count,
        )

    def _generate_daily_report(self) -> None:
        """Generate end-of-day summary report."""
        try:
            _LOG.info("Generating daily summary report...")
            report = self.reporter.generate_daily_summary()
            _LOG.info("Daily report saved to reports/")
            # Print summary to console
            print("\n" + report)
        except Exception as e:
            _LOG.error("Error generating daily report: %s", e)

    def _shutdown(self) -> None:
        """Clean shutdown of bot."""
        _LOG.info("Closing all positions...")

        # Close all positions
        for ticker in list(self._positions.keys()):
            try:
                position = self._positions[ticker]
                current_data = self._fetch_price_data(ticker, days=1)
                if current_data is not None and len(current_data) > 0:
                    current_price = current_data["close"].iloc[-1]

                    action = "sell" if position["direction"] == "long" else "buy"

                    # Calculate P&L
                    if position["direction"] == "long":
                        pnl = (current_price - position["entry_price"]) * position["quantity"]
                    else:
                        pnl = (position["entry_price"] - current_price) * position["quantity"]

                    if self.executor.execute_trade(
                        ticker=ticker,
                        action=action,
                        quantity=position["quantity"],
                        price=current_price,
                    ):
                        # Record exit trade
                        self.reporter.record_trade(
                            ticker=ticker,
                            action=action,
                            quantity=position["quantity"],
                            price=current_price,
                            strategy=position["strategy"],
                            pnl=pnl,
                        )

                    _LOG.info("%s: Position closed on shutdown - P&L: %+.2f", ticker, pnl)

            except Exception as e:
                _LOG.error("Error closing position for %s: %s", ticker, e)

        # Generate final daily report
        self._generate_daily_report()

        _LOG.info("Bot shutdown complete")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Multi-strategy trading bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run in simulation mode (no real trades)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run with real trading (USE WITH CAUTION)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Trading capital (default: $10,000)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/trading_bot.log"),
        ],
    )

    # Create logs directory
    Path("logs").mkdir(exist_ok=True)

    # Determine if dry run
    dry_run = not args.live

    if not dry_run:
        _LOG.warning("=" * 80)
        _LOG.warning("LIVE TRADING MODE - REAL MONEY AT RISK")
        _LOG.warning("=" * 80)
        response = input("Are you sure you want to proceed? (type 'YES' to confirm): ")
        if response != "YES":
            _LOG.info("Live trading cancelled")
            return

    # Create configuration
    config = BotConfig.default(strategy="trend_following", capital=args.capital)

    # Create and run bot
    bot = MultiStrategyBot(config=config, dry_run=dry_run)
    bot.run()


if __name__ == "__main__":
    main()
