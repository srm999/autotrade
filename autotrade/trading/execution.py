"""Execution helpers for translating signals into Charles Schwab orders."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from autotrade.broker import SchwabClient
from autotrade.config import BotConfig
from autotrade.strategy.base import Signal
from autotrade.trading.circuit_breaker import CircuitBreaker
from autotrade.trading.trade_logger import TradeLogger, TradeRecord
from autotrade.utils.time_utils import now_utc

_LOG = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order status states."""
    SUBMITTED = "submitted"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class OrderRecord:
    """Tracks submitted order details."""
    order_id: str | None
    ticker: str
    quantity: int
    side: str
    price: float
    timestamp: datetime
    status: OrderStatus
    reason: str
    metadata: dict[str, Any]


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
        client: SchwabClient,
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
        self._orders: dict[str, OrderRecord] = {}  # Track submitted orders

        # Initialize circuit breaker for risk management
        cb_config = config.circuit_breaker
        self._circuit_breaker = CircuitBreaker(
            max_daily_loss=cb_config.max_daily_loss,
            max_consecutive_losses=cb_config.max_consecutive_losses,
            max_trades_per_hour=cb_config.max_trades_per_hour,
            enabled=cb_config.enabled,
        )

        self._reconcile_positions()

    def _reconcile_positions(self) -> None:
        """Load current positions from broker to reconcile internal state.

        This ensures position tracking is accurate on startup, preventing
        over-leveraging or incorrect position size calculations.
        """
        try:
            holdings = self._client.get_positions()
            if not holdings:
                _LOG.info("Position reconciliation: no positions found at broker")
                return

            reconciled_count = 0
            for ticker, holding in holdings.items():
                quantity = holding.get("quantity")
                avg_cost = holding.get("average_buy_price")

                if quantity is None or avg_cost is None:
                    _LOG.warning(
                        "Position reconciliation: skipping %s, missing data (quantity=%s, avg_cost=%s)",
                        ticker,
                        quantity,
                        avg_cost,
                    )
                    continue

                qty_float = float(quantity)
                cost_float = float(avg_cost)

                if qty_float > 0:
                    self._positions[ticker] = HeldPosition(
                        quantity=qty_float,
                        avg_cost=cost_float,
                    )
                    reconciled_count += 1
                    _LOG.info(
                        "Position reconciliation: loaded %s position (qty=%.2f, avg_cost=%.2f)",
                        ticker,
                        qty_float,
                        cost_float,
                    )

            _LOG.info("Position reconciliation complete: loaded %d position(s)", reconciled_count)

        except Exception as exc:
            _LOG.error("Position reconciliation failed: %s", exc, exc_info=True)
            # Don't raise - allow bot to continue but log error for investigation

    def handle_signal(self, signal: Signal) -> None:
        if signal.side not in {"buy", "sell", "flat"}:
            _LOG.debug("Ignoring unsupported signal side %s", signal.side)
            return

        # Check circuit breaker before executing any trades
        if not self._circuit_breaker.can_trade():
            _LOG.warning(
                "Circuit breaker prevents trading: %s (signal=%s %s)",
                self._circuit_breaker.trip_reason(),
                signal.side,
                signal.ticker,
            )
            return
        limits = PositionLimits(
            max_position_size=self._config.strategy.max_position_size,
            max_total_exposure=self._config.strategy.max_total_exposure,
        )
        price = self._client.get_last_trade_price(signal.ticker)
        if price <= 0:
            _LOG.info("Skipping %s order; invalid price %.2f", signal.ticker, price)
            return
        portfolio = self._client.get_portfolio_profile()
        total_exposure = float(portfolio.get("market_value", 0.0) or 0.0)
        cash_available = float(portfolio.get("cash_available_for_trading", 0.0) or 0.0)
        holdings = self._client.get_positions()
        current_shares = self._current_shares(holdings, signal.ticker)
        tracked = self._positions.get(signal.ticker)
        tracked_shares = tracked.quantity if tracked else 0.0
        timestamp = now_utc()

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
                # Record trade outcome with circuit breaker
                self._circuit_breaker.record_trade(signal.ticker, realized)
            return

        if signal.side == "buy":
            quantity = self._resolve_buy_quantity(
                signal, price, limits.max_position_size, cash_available
            )
            if quantity <= 0:
                _LOG.info(
                    "Skipping %s buy; insufficient cash (available %.2f, price %.2f)",
                    signal.ticker,
                    cash_available,
                    price,
                )
                return
            projected = total_exposure + price * quantity
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
            # Record trade outcome with circuit breaker
            self._circuit_breaker.record_trade(signal.ticker, realized)

    def _resolve_buy_quantity(
        self,
        signal: Signal,
        price: float,
        max_position_size: float,
        cash_available: float,
    ) -> int:
        if signal.quantity and signal.quantity > 0:
            target = int(signal.quantity)
            affordable = int(cash_available // price) if price > 0 else 0
            if affordable <= 0:
                return 0
            return min(target, affordable)
        notional = max_position_size
        if signal.metadata and "notional" in signal.metadata:
            notional = float(signal.metadata["notional"])
        notional = min(notional, cash_available)
        if notional < price:
            return 0
        quantity = int(notional // price)
        if quantity <= 0 and cash_available >= price:
            quantity = 1
        return quantity

    def _current_shares(self, holdings: dict[str, dict[str, Any]], ticker: str) -> float:
        holding = holdings.get(ticker)
        if not holding:
            return 0.0
        quantity = holding.get("quantity")
        if quantity is None:
            return 0.0
        return float(quantity)

    def _extract_order_id(self, order_response: Any) -> str | None:
        """Extract order ID from Schwab API response.

        The Schwab API may return order IDs in various formats.
        This method attempts to extract the order ID with fallback strategies.
        """
        if not order_response:
            return None

        # Try direct access if response is a dict
        if isinstance(order_response, dict):
            order_id = order_response.get("orderId") or order_response.get("order_id")
            if order_id:
                return str(order_id)

        # Try accessing as object attribute
        try:
            if hasattr(order_response, "order_id"):
                return str(order_response.order_id)
            if hasattr(order_response, "orderId"):
                return str(order_response.orderId)
        except (AttributeError, TypeError):
            pass

        # Try converting response to string and extracting ID pattern
        try:
            response_str = str(order_response)
            # Look for patterns like "order_id: 12345" or "orderId: 12345"
            import re
            match = re.search(r'order[_\s]?id[:\s]+(\d+)', response_str, re.IGNORECASE)
            if match:
                return match.group(1)
        except (TypeError, AttributeError):
            pass

        _LOG.debug("Could not extract order ID from response: %s", order_response)
        return None

    def check_order_status(self, order_id: str) -> OrderStatus:
        """Check the current status of an order and update internal tracking.

        Args:
            order_id: The order ID to check

        Returns:
            OrderStatus enum value indicating current order state
        """
        if order_id not in self._orders:
            _LOG.warning("Order ID %s not found in tracking", order_id)
            return OrderStatus.UNKNOWN

        # Paper trading orders are always assumed filled
        if self._paper:
            return OrderStatus.FILLED

        try:
            status_info = self._client.get_order_status(order_id)
            if not status_info:
                _LOG.warning("Could not retrieve status for order %s", order_id)
                return OrderStatus.UNKNOWN

            status_str = status_info.get("status", "").upper()
            order_record = self._orders[order_id]

            # Map Schwab status strings to our OrderStatus enum
            if status_str in ("FILLED", "EXECUTED"):
                order_record.status = OrderStatus.FILLED
                _LOG.info(
                    "Order %s filled: %s %s x%d",
                    order_id,
                    order_record.side,
                    order_record.ticker,
                    order_record.quantity,
                )
            elif status_str in ("REJECTED", "FAILED"):
                order_record.status = OrderStatus.REJECTED
                _LOG.error(
                    "Order %s rejected: %s %s x%d",
                    order_id,
                    order_record.side,
                    order_record.ticker,
                    order_record.quantity,
                )
            elif status_str in ("CANCELLED", "CANCELED"):
                order_record.status = OrderStatus.CANCELLED
                _LOG.warning(
                    "Order %s cancelled: %s %s x%d",
                    order_id,
                    order_record.side,
                    order_record.ticker,
                    order_record.quantity,
                )
            elif status_str in ("WORKING", "PENDING", "QUEUED"):
                # Order still pending
                pass
            else:
                _LOG.debug("Unknown order status '%s' for order %s", status_str, order_id)

            return order_record.status

        except Exception as exc:
            _LOG.error("Failed to check order status for %s: %s", order_id, exc, exc_info=True)
            return OrderStatus.UNKNOWN

    def get_pending_orders(self) -> list[OrderRecord]:
        """Get all orders that are still in SUBMITTED status.

        Returns:
            List of OrderRecord objects with SUBMITTED status
        """
        return [
            order
            for order in self._orders.values()
            if order.status == OrderStatus.SUBMITTED
        ]

    def get_circuit_breaker_status(self) -> dict[str, any]:
        """Get current circuit breaker status.

        Returns:
            Dict with circuit breaker state information
        """
        return self._circuit_breaker.get_status()

    def reset_circuit_breaker(self) -> None:
        """Reset circuit breaker for a new trading day.

        Call this at the start of each trading session.
        """
        self._circuit_breaker.reset_daily()
        _LOG.info("Circuit breaker reset for new trading session")

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

        timestamp = now_utc()

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
            # Track paper orders with synthetic ID
            order_id = f"PAPER_{ticker}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
            order = OrderRecord(
                order_id=order_id,
                ticker=ticker,
                quantity=quantity,
                side=side,
                price=price,
                timestamp=timestamp,
                status=OrderStatus.FILLED,  # Paper orders assumed filled
                reason=reason,
                metadata=metadata,
            )
            self._orders[order_id] = order
            return True

        # Live order submission with error handling
        try:
            order_response = self._client.submit_market_order(ticker, quantity=quantity, side=side)
            order_id = self._extract_order_id(order_response)

            order = OrderRecord(
                order_id=order_id,
                ticker=ticker,
                quantity=quantity,
                side=side,
                price=price,
                timestamp=timestamp,
                status=OrderStatus.SUBMITTED,
                reason=reason,
                metadata=metadata,
            )

            if order_id:
                self._orders[order_id] = order
                _LOG.info(
                    "Submitted %s order: %s x%s @ %.2f (order_id=%s, reason=%s)",
                    side,
                    ticker,
                    quantity,
                    price,
                    order_id,
                    reason,
                )
            else:
                _LOG.warning(
                    "Submitted %s order but could not extract order ID: %s x%s (reason=%s)",
                    side,
                    ticker,
                    quantity,
                    reason,
                )

            return True

        except ValueError as exc:
            # Invalid parameters (quantity, side, etc.)
            _LOG.error(
                "Order submission failed due to invalid parameters: %s %s x%s - %s",
                side,
                ticker,
                quantity,
                exc,
            )
            return False

        except RuntimeError as exc:
            # API errors, connection issues
            _LOG.error(
                "Order submission failed due to API error: %s %s x%s - %s",
                side,
                ticker,
                quantity,
                exc,
                exc_info=True,
            )
            return False

        except Exception as exc:
            # Unexpected errors - log with full context
            _LOG.error(
                "Order submission failed with unexpected error: %s %s x%s - %s",
                side,
                ticker,
                quantity,
                exc,
                exc_info=True,
            )
            return False

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


class TradeExecutor:
    """Simplified trade executor for multi-strategy bot."""

    def __init__(self, broker: SchwabClient | None, circuit_breaker: CircuitBreaker, dry_run: bool = True):
        """
        Initialize trade executor.

        Args:
            broker: Schwab client (None if dry run)
            circuit_breaker: Circuit breaker for risk management
            dry_run: If True, simulate trades without executing
        """
        self.broker = broker
        self.circuit_breaker = circuit_breaker
        self.dry_run = dry_run
        self._trade_count = 0

    def execute_trade(
        self,
        ticker: str,
        action: str,
        quantity: int,
        price: float,
    ) -> bool:
        """
        Execute a trade.

        Args:
            ticker: Stock ticker
            action: "buy" or "sell"
            quantity: Number of shares
            price: Price per share

        Returns:
            True if trade executed successfully
        """
        # Check circuit breaker
        if not self.circuit_breaker.can_trade():
            _LOG.warning(
                "Circuit breaker prevents trading: %s",
                self.circuit_breaker.trip_reason(),
            )
            return False

        if quantity <= 0:
            _LOG.warning("%s: Invalid quantity %d", ticker, quantity)
            return False

        # Log the trade
        _LOG.info(
            "%s: %s %d shares @ $%.2f (total: $%.2f) [%s]",
            ticker,
            action.upper(),
            quantity,
            price,
            quantity * price,
            "DRY RUN" if self.dry_run else "LIVE",
        )

        if self.dry_run:
            # Simulate successful execution
            self._trade_count += 1
            return True

        # Execute real trade via broker
        try:
            if action == "buy":
                order_id = self.broker.place_market_order(ticker, quantity, "buy")
            elif action == "sell":
                order_id = self.broker.place_market_order(ticker, quantity, "sell")
            else:
                _LOG.error("%s: Unknown action '%s'", ticker, action)
                return False

            if order_id:
                _LOG.info("%s: Trade executed, order_id=%s", ticker, order_id)
                self._trade_count += 1
                return True
            else:
                _LOG.error("%s: Trade failed (no order_id)", ticker)
                return False

        except Exception as e:
            _LOG.error("%s: Trade execution failed: %s", ticker, e)
            return False

    @property
    def trade_count(self) -> int:
        """Get total number of trades executed."""
        return self._trade_count
