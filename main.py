"""Command-line entry point for the Robinhood intraday trading bot."""
from __future__ import annotations

import argparse
import logging

from autotrade.broker.robinhood_client import RobinhoodClient
from autotrade.config import BotConfig, RobinhoodCredentials
from autotrade.trading.loop import run_trading_loop


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Intraday Robinhood trading bot")
    parser.add_argument("--dry-run", action="store_true", help="Run without placing live orders")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    config = BotConfig.default()
    credentials = RobinhoodCredentials.from_env()
    mode = "paper" if args.dry_run else "live"
    logging.getLogger(__name__).info("Starting %s bot with strategy %s", mode, config.strategy.name)
    with RobinhoodClient(credentials) as client:
        run_trading_loop(client, config, paper_trading=args.dry_run)


if __name__ == "__main__":
    main()
