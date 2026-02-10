"""Intraday trading loop that wires together strategy, data, and execution."""
from __future__ import annotations

import logging
import signal
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Callable, Iterator

from autotrade.broker import SchwabClient
from autotrade.config import BotConfig
from autotrade.data.market import MarketDataService
from autotrade.strategy import Signal, create_strategy
from autotrade.trading.execution import ExecutionEngine
from autotrade.trading.reporting import DailySummaryReporter
from autotrade.trading.trade_logger import TradeLogger
from autotrade.utils.market_hours import is_market_open, get_market_status
from autotrade.utils.time_utils import now_utc

import httpx

_LOG = logging.getLogger(__name__)


@contextmanager
def graceful_shutdown() -> Iterator[Callable[[], bool]]:
    terminate = False

    def _handler(signum, frame):  # pragma: no cover - signal handling
        nonlocal terminate
        _LOG.info("Received signal %s, shutting down", signum)
        terminate = True

    original_int = signal.getsignal(signal.SIGINT)
    original_term = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
    try:
        yield lambda: terminate
    finally:
        signal.signal(signal.SIGINT, original_int)
        signal.signal(signal.SIGTERM, original_term)


def run_trading_loop(client: SchwabClient, config: BotConfig, *, paper_trading: bool = False) -> None:
    # Validate market hours before starting
    market_status = get_market_status()
    if not market_status["is_open"]:
        _LOG.warning(
            "Market is currently closed (weekend=%s, holiday=%s). "
            "Next market open: %s (in %.1f hours)",
            market_status["is_weekend"],
            market_status["is_holiday"],
            market_status["next_open"].strftime("%Y-%m-%d %H:%M %Z"),
            market_status["seconds_until_open"] / 3600,
        )
        if not paper_trading:
            _LOG.error("Cannot start live trading when market is closed. Exiting.")
            return
        _LOG.info("Paper trading mode: continuing despite closed market")

    data_service = MarketDataService(client)
    strategy = create_strategy(config, data_service)
    trade_logger = TradeLogger()
    execution = ExecutionEngine(client, config, paper_trading=paper_trading, trade_logger=trade_logger)
    polling_seconds = config.polling_interval_seconds
    mode = "paper" if paper_trading else "live"
    _LOG.info("Starting %s trading loop for %s", mode, config.strategy.tickers)
    _LOG.info("Market status: Regular hours=%s, Extended hours=%s",
              market_status["is_regular_hours"],
              market_status["is_extended_hours"])
    reporter = DailySummaryReporter(config)
    exit_reason = "market_closed"
    portfolio_error_logged = False
    with graceful_shutdown() as should_stop:
        while True:
            now = now_utc()
            try:
                portfolio_snapshot = client.get_portfolio_profile()
            except (httpx.HTTPError, RuntimeError) as exc:
                # API/network errors when fetching portfolio
                if not portfolio_error_logged:
                    _LOG.warning("Failed to fetch portfolio profile (API error): %s", exc)
                    portfolio_error_logged = True
                portfolio_snapshot = {}
            except (ValueError, TypeError) as exc:
                # Data parsing errors
                if not portfolio_error_logged:
                    _LOG.error("Failed to parse portfolio profile: %s", exc, exc_info=True)
                    portfolio_error_logged = True
                portfolio_snapshot = {}
            else:
                portfolio_error_logged = False
                reporter.record_portfolio(timestamp=now, profile=portfolio_snapshot)

            # Check if market is still open (validates holidays, weekends, and regular hours)
            if not is_market_open(now, allow_extended_hours=False):
                _LOG.info("Market is no longer open, exiting loop")
                exit_reason = "market_closed"
                break

            # Also check configured trading window
            if now.time() >= config.trading_window.market_close:
                _LOG.info("Trading window closed (configured time reached), exiting loop")
                exit_reason = "trading_window_closed"
                break
            flattened = False
            if strategy.should_flatten(timestamp=now):
                diagnostics = strategy.diagnostics(timestamp=now)
                reporter.record_flatten(timestamp=now, diagnostics=diagnostics)
                for ticker in config.strategy.tickers:
                    execution.handle_signal(Signal(ticker=ticker, side="flat"))
                flattened = True
            if not flattened:
                for ticker in config.strategy.tickers:
                    try:
                        quote = data_service.latest_quote(ticker)
                        signal_out = strategy.on_quote(quote, timestamp=now)
                        diagnostics = strategy.diagnostics(timestamp=now)
                        reporter.record_quote(quote, diagnostics)
                        if signal_out:
                            reporter.record_signal(signal_out, diagnostics, timestamp=now)
                            execution.handle_signal(signal_out)
                    except (httpx.HTTPError, RuntimeError) as exc:
                        # API/network errors when fetching quotes
                        reporter.record_error(ticker=ticker, error=exc, timestamp=now)
                        _LOG.warning("API error processing %s: %s", ticker, exc)
                    except (ValueError, TypeError, KeyError) as exc:
                        # Data validation or processing errors
                        reporter.record_error(ticker=ticker, error=exc, timestamp=now)
                        _LOG.error("Data error processing %s: %s", ticker, exc, exc_info=True)
                    except Exception as exc:
                        # Catch-all for unexpected errors - log with full traceback
                        reporter.record_error(ticker=ticker, error=exc, timestamp=now)
                        _LOG.exception("Unexpected error processing %s: %s", ticker, exc)
            if should_stop():
                _LOG.info("Received shutdown request, stopping loop")
                exit_reason = "shutdown"
                break
            time.sleep(polling_seconds)
    summary_text = reporter.finalize(end_time=now_utc(), reason=exit_reason)
    _LOG.info("Daily summary:\n%s", summary_text)
