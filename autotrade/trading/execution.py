"""Execution helpers for translating signals into Robinhood orders."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from autotrade.broker.robinhood_client import RobinhoodClient
from autotrade.config import BotConfig
from autotrade.strategy.base import Signal
from autotrade.trading.trade_logger import TradeLogger, TradeRecord

_LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class PositionLimits:
    max_position_size: float
    max_total_exposure: float


@dataclass(slots=True)
class HeldPosition:
    quantity: float = 0.0
    avg_cost: float = 0.0


class ExecutionEngine:
    def __init__(
        self,
        client: RobinhoodClient,
        config: BotConfig,
        *,
        paper_trading: bool = False,
        trade_logger: TradeLogger | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._paper = paper_trading
        self._trade_logger = trade_logger
        self._positions: dict[str, HeldPosition] = {}

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
        tracked = self._positions.get(signal.ticker)
        tracked_shares = tracked.quantity if tracked else 0.0
        timestamp = datetime.now()

        if signal.side == "flat":
            quantity_to_sell = int(max(current_shares, tracked_shares))
            if quantity_to_sell <= 0:
                return
            reason, metadata = "flatten", {}
            if self._submit(signal.ticker, quantity_to_sell, "sell", price, reason=reason, metadata=metadata):
                realized, position = self._update_after_sell(signal.ticker, quantity_to_sell, price)
                self._log_trade(
                    ticker=signal.ticker,
                    side="sell",
                    quantity=quantity_to_sell,
                    price=price,
                    timestamp=timestamp,
                    reason=reason,
                    metadata=metadata,
                    realized_pnl=realized,
                    position=position,
                )
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
            reason, metadata = self._extract_reason_and_metadata(signal.metadata, default="entry")
            if self._submit(signal.ticker, quantity, "buy", price, reason=reason, metadata=metadata):
                position = self._update_after_buy(signal.ticker, quantity, price)
                self._log_trade(
                    ticker=signal.ticker,
                    side="buy",
                    quantity=quantity,
                    price=price,
                    timestamp=timestamp,
                    reason=reason,
                    metadata=metadata,
                    realized_pnl=0.0,
                    position=position,
                )
            return

        if current_shares <= 0:
            if tracked_shares <= 0:
                _LOG.info("Skipping %s sell; no exposure", signal.ticker)
                return
            current_shares = tracked_shares
        target_quantity = signal.quantity if signal.quantity else current_shares
        available = max(current_shares, tracked_shares)
        quantity = min(int(target_quantity), int(available))
        if quantity <= 0:
            return
        reason, metadata = self._extract_reason_and_metadata(signal.metadata, default="exit")
        if self._submit(signal.ticker, quantity, "sell", price, reason=reason, metadata=metadata):
            realized, position = self._update_after_sell(signal.ticker, quantity, price)
            self._log_trade(
                ticker=signal.ticker,
                side="sell",
                quantity=quantity,
                price=price,
                timestamp=timestamp,
                reason=reason,
                metadata=metadata,
                realized_pnl=realized,
                position=position,
            )

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

    def _submit(
        self,
        ticker: str,
        quantity: int,
        side: str,
        price: float,
        *,
        reason: str,
        metadata: dict[str, Any],
    ) -> bool:
        if quantity <= 0:
            return False
        if self._paper:
            _LOG.info(
                "Paper trade: %s %s x%s @ %.2f (reason=%s, metadata=%s)",
                side,
                ticker,
                quantity,
                price,
                reason,
                metadata,
            )
            return True
        self._client.submit_market_order(ticker, quantity=quantity, side=side)
        _LOG.info("Submitted %s order: %s x%s (reason=%s)", side, ticker, quantity, reason)
        return True

    def _update_after_buy(self, ticker: str, quantity: int, price: float) -> HeldPosition:
        position = self._positions.get(ticker, HeldPosition())
        total_cost = position.avg_cost * position.quantity + price * quantity
        position.quantity += quantity
        position.avg_cost = total_cost / position.quantity if position.quantity else 0.0
        self._positions[ticker] = position
        return position

    def _update_after_sell(self, ticker: str, quantity: int, price: float) -> tuple[float, HeldPosition]:
        position = self._positions.get(ticker, HeldPosition())
        sell_qty = min(quantity, position.quantity) if position.quantity else 0.0
        realized = (price - position.avg_cost) * sell_qty if sell_qty else 0.0
        position.quantity -= sell_qty
        if position.quantity <= 0:
            position.quantity = 0.0
            position.avg_cost = 0.0
            if ticker in self._positions:
                self._positions.pop(ticker)
        else:
            self._positions[ticker] = position
        return realized, position

    def _log_trade(
        self,
        *,
        ticker: str,
        side: str,
        quantity: int,
        price: float,
        timestamp: datetime,
        reason: str,
        metadata: dict[str, Any],
        realized_pnl: float,
        position: HeldPosition,
    ) -> None:
        if not self._trade_logger:
            return
        record = TradeRecord(
            timestamp=timestamp,
            ticker=ticker,
            side=side,
            quantity=quantity,
            price=price,
            notional=price * quantity,
            reason=reason,
            metadata=metadata,
            realized_pnl=realized_pnl,
            cumulative_pnl=0.0,  # computed by logger
            position_quantity=position.quantity,
            position_avg_cost=position.avg_cost,
        )
        self._trade_logger.record(record)

    @staticmethod
    def _extract_reason_and_metadata(
        payload: dict[str, Any] | str | None,
        *,
        default: str,
    ) -> tuple[str, dict[str, Any]]:
        if payload is None:
            return default, {}
        if isinstance(payload, str):
            return payload, {}
        if isinstance(payload, dict):
            reason_value = payload.get("reason", default)
            return str(reason_value), payload
        return default, {}
