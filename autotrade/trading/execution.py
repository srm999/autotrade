"""Execution helpers for translating signals into Robinhood orders."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from autotrade.broker.robinhood_client import RobinhoodClient
from autotrade.config import BotConfig
from autotrade.strategy.base import Signal

_LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class PositionLimits:
    max_position_size: float
    max_total_exposure: float


class ExecutionEngine:
    def __init__(self, client: RobinhoodClient, config: BotConfig, *, paper_trading: bool = False) -> None:
        self._client = client
        self._config = config
        self._paper = paper_trading

    def _total_exposure(self) -> float:
        portfolio = self._client.get_portfolio_profile()
        return float(portfolio.get("market_value", 0.0))

    def handle_signal(self, signal: Signal) -> None:
        if signal.side not in {"buy", "sell", "flat"}:
            _LOG.debug("Ignoring unsupported signal side %s", signal.side)
            return
        limits = PositionLimits(
            max_position_size=self._config.strategy.max_position_size,
            max_total_exposure=self._config.strategy.max_total_exposure,
        )
        price = self._client.get_last_trade_price(signal.ticker)
        if price <= 0:
            _LOG.info("Skipping %s order; invalid price %.2f", signal.ticker, price)
            return
        holdings = self._client.get_positions()
        current_shares = self._current_shares(holdings, signal.ticker)

        if signal.side == "flat":
            if current_shares <= 0:
                return
            self._submit(signal.ticker, int(current_shares), "sell", price, reason="flatten")
            return

        if signal.side == "buy":
            quantity = self._resolve_buy_quantity(signal, price, limits.max_position_size)
            if quantity <= 0:
                return
            projected = self._total_exposure() + price * quantity
            if projected > limits.max_total_exposure:
                _LOG.info(
                    "Skipping %s buy; projected exposure %.2f exceeds limit %.2f",
                    signal.ticker,
                    projected,
                    limits.max_total_exposure,
                )
                return
            self._submit(signal.ticker, quantity, "buy", price, reason=signal.metadata or {})
            return

        if current_shares <= 0:
            _LOG.info("Skipping %s sell; no exposure", signal.ticker)
            return
        target_quantity = signal.quantity if signal.quantity else current_shares
        quantity = min(int(target_quantity), int(current_shares))
        if quantity <= 0:
            return
        self._submit(signal.ticker, quantity, "sell", price, reason=signal.metadata or {})

    def _resolve_buy_quantity(self, signal: Signal, price: float, max_position_size: float) -> int:
        if signal.quantity and signal.quantity > 0:
            return int(signal.quantity)
        notional = max_position_size
        if signal.metadata and "notional" in signal.metadata:
            notional = float(signal.metadata["notional"])
        quantity = int(notional // price)
        return max(1, quantity)

    def _current_shares(self, holdings: dict[str, dict[str, Any]], ticker: str) -> float:
        holding = holdings.get(ticker)
        if not holding:
            return 0.0
        quantity = holding.get("quantity")
        if quantity is None:
            return 0.0
        return float(quantity)

    def _submit(self, ticker: str, quantity: int, side: str, price: float, reason: dict[str, Any] | str) -> None:
        if quantity <= 0:
            return
        if self._paper:
            _LOG.info("Paper trade: %s %s x%s @ %.2f (%s)", side, ticker, quantity, price, reason)
            return
        self._client.submit_market_order(ticker, quantity=quantity, side=side)
        _LOG.info("Submitted %s order: %s x%s (%s)", side, ticker, quantity, reason)
