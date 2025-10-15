"""Intraday trading loop that wires together strategy, data, and execution."""
from __future__ import annotations

import logging
import signal
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Callable, Iterator

from autotrade.broker.robinhood_client import RobinhoodClient
from autotrade.config import BotConfig
from autotrade.data.market import MarketDataService
from autotrade.strategy import DualMAMeanReversionStrategy, Signal
from autotrade.trading.execution import ExecutionEngine
from autotrade.trading.trade_logger import TradeLogger

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


def run_trading_loop(client: RobinhoodClient, config: BotConfig, *, paper_trading: bool = False) -> None:
    data_service = MarketDataService(client)
    strategy = DualMAMeanReversionStrategy(config, data_service)
    trade_logger = TradeLogger()
    execution = ExecutionEngine(client, config, paper_trading=paper_trading, trade_logger=trade_logger)
    polling_seconds = config.polling_interval_seconds
    mode = "paper" if paper_trading else "live"
    _LOG.info("Starting %s trading loop for %s", mode, config.strategy.tickers)
    with graceful_shutdown() as should_stop:
        while True:
            now = datetime.now()
            if now.time() >= config.trading_window.market_close:
                _LOG.info("Market closed, exiting loop")
                break
            flattened = False
            if strategy.should_flatten(timestamp=now):
                for ticker in config.strategy.tickers:
                    execution.handle_signal(Signal(ticker=ticker, side="flat"))
                flattened = True
            if not flattened:
                for ticker in config.strategy.tickers:
                    try:
                        quote = data_service.latest_quote(ticker)
                        signal_out = strategy.on_quote(quote, timestamp=now)
                        if signal_out:
                            execution.handle_signal(signal_out)
                    except Exception as exc:  # pragma: no cover - live trading guard
                        _LOG.exception("Error processing %s: %s", ticker, exc)
            if should_stop():
                _LOG.info("Received shutdown request, stopping loop")
                break
            time.sleep(polling_seconds)
