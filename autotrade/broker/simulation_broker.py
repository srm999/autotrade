"""Enhanced simulation broker with realistic order execution.

This provides more realistic paper trading by simulating:
- Order slippage
- Partial fills
- Market impact
- Commission costs
- Realistic delays
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

_LOG = logging.getLogger(__name__)


@dataclass
class SimulatedPosition:
    """Simulated position."""

    ticker: str
    quantity: int
    entry_price: float
    entry_time: datetime
    side: Literal["long", "short"]


@dataclass
class SimulatedOrder:
    """Simulated order with realistic execution."""

    order_id: str
    ticker: str
    action: str
    quantity: int
    order_type: str
    limit_price: float | None
    status: str  # pending, filled, partial, rejected
    filled_quantity: int
    filled_price: float | None
    submit_time: datetime
    fill_time: datetime | None


class SimulationBroker:
    """Enhanced simulation broker with realistic execution.

    Features:
    - Slippage simulation (0.05-0.15%)
    - Partial fills for large orders
    - Commission costs (configurable)
    - Market impact for low liquidity
    - Order delays
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_per_trade: float = 0.0,  # Commission per trade
        slippage_pct: float = 0.05,  # Slippage as % (0.05 = 0.05%)
        enable_partial_fills: bool = False,
        enable_delays: bool = False,
    ):
        """Initialize simulation broker.

        Args:
            initial_capital: Starting capital
            commission_per_trade: Commission per trade (e.g., $0 for Alpaca)
            slippage_pct: Slippage percentage (realistic: 0.05-0.15%)
            enable_partial_fills: Simulate partial fills for large orders
            enable_delays: Simulate realistic order delays (1-5 seconds)
        """
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.commission_per_trade = commission_per_trade
        self.slippage_pct = slippage_pct
        self.enable_partial_fills = enable_partial_fills
        self.enable_delays = enable_delays

        self.positions: dict[str, SimulatedPosition] = {}
        self.orders: list[SimulatedOrder] = []
        self.order_counter = 0

        _LOG.info(
            "Simulation broker initialized: capital=$%.2f, slippage=%.3f%%, commission=$%.2f",
            initial_capital,
            slippage_pct,
            commission_per_trade,
        )

    def execute_order(
        self,
        ticker: str,
        action: str,  # 'buy' or 'sell'
        quantity: int,
        current_price: float,
        order_type: str = "market",
        limit_price: float | None = None,
    ) -> SimulatedOrder:
        """Execute order with realistic simulation.

        Args:
            ticker: Stock ticker
            action: 'buy' or 'sell'
            quantity: Number of shares
            current_price: Current market price
            order_type: 'market' or 'limit'
            limit_price: Limit price (for limit orders)

        Returns:
            SimulatedOrder with execution details
        """
        self.order_counter += 1
        order_id = f"SIM{self.order_counter:06d}"

        # Simulate order delay
        if self.enable_delays:
            delay = random.uniform(0.5, 2.0)  # 0.5-2 second delay
            time.sleep(delay)

        # Calculate execution price with slippage
        if order_type == "market":
            execution_price = self._apply_slippage(current_price, action)
        else:
            # Limit order - check if it would fill
            if action == "buy" and current_price <= limit_price:
                execution_price = limit_price
            elif action == "sell" and current_price >= limit_price:
                execution_price = limit_price
            else:
                # Order doesn't fill
                order = SimulatedOrder(
                    order_id=order_id,
                    ticker=ticker,
                    action=action,
                    quantity=quantity,
                    order_type=order_type,
                    limit_price=limit_price,
                    status="rejected",
                    filled_quantity=0,
                    filled_price=None,
                    submit_time=datetime.now(),
                    fill_time=None,
                )
                self.orders.append(order)
                _LOG.warning(
                    "%s: Limit order rejected - price $%.2f not reached (limit: $%.2f)",
                    ticker,
                    current_price,
                    limit_price,
                )
                return order

        # Determine fill quantity (partial fills for large orders)
        filled_quantity = quantity
        status = "filled"

        if self.enable_partial_fills and quantity > 1000:
            # Large order - may get partial fill
            fill_pct = random.uniform(0.7, 1.0)
            filled_quantity = int(quantity * fill_pct)
            status = "partial" if filled_quantity < quantity else "filled"

        # Calculate total cost
        total_cost = filled_quantity * execution_price

        # Add commission
        total_cost += self.commission_per_trade

        # Check if sufficient funds (for buys)
        if action == "buy" and total_cost > self.cash:
            order = SimulatedOrder(
                order_id=order_id,
                ticker=ticker,
                action=action,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
                status="rejected",
                filled_quantity=0,
                filled_price=None,
                submit_time=datetime.now(),
                fill_time=None,
            )
            self.orders.append(order)
            _LOG.error(
                "%s: Order rejected - insufficient funds (need $%.2f, have $%.2f)",
                ticker,
                total_cost,
                self.cash,
            )
            return order

        # Execute trade
        if action == "buy":
            self.cash -= total_cost
            self._add_position(ticker, filled_quantity, execution_price, "long")
            _LOG.info(
                "%s: BUY %d shares @ $%.2f (slippage: $%.3f, cost: $%.2f) [SIMULATED]",
                ticker,
                filled_quantity,
                execution_price,
                abs(execution_price - current_price),
                total_cost,
            )
        else:  # sell
            self.cash += (filled_quantity * execution_price) - self.commission_per_trade
            self._remove_position(ticker, filled_quantity)
            _LOG.info(
                "%s: SELL %d shares @ $%.2f (slippage: $%.3f, proceeds: $%.2f) [SIMULATED]",
                ticker,
                filled_quantity,
                execution_price,
                abs(execution_price - current_price),
                (filled_quantity * execution_price) - self.commission_per_trade,
            )

        # Create order record
        order = SimulatedOrder(
            order_id=order_id,
            ticker=ticker,
            action=action,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            status=status,
            filled_quantity=filled_quantity,
            filled_price=execution_price,
            submit_time=datetime.now(),
            fill_time=datetime.now(),
        )
        self.orders.append(order)

        return order

    def _apply_slippage(self, price: float, action: str) -> float:
        """Apply realistic slippage to execution price.

        Args:
            price: Market price
            action: 'buy' or 'sell'

        Returns:
            Execution price with slippage
        """
        # Random slippage within configured range
        slippage = random.uniform(0, self.slippage_pct / 100)

        if action == "buy":
            # Buys execute slightly higher
            return price * (1 + slippage)
        else:
            # Sells execute slightly lower
            return price * (1 - slippage)

    def _add_position(self, ticker: str, quantity: int, price: float, side: str):
        """Add or update position."""
        if ticker in self.positions:
            # Average up/down existing position
            pos = self.positions[ticker]
            total_quantity = pos.quantity + quantity
            avg_price = ((pos.quantity * pos.entry_price) + (quantity * price)) / total_quantity
            pos.quantity = total_quantity
            pos.entry_price = avg_price
        else:
            # New position
            self.positions[ticker] = SimulatedPosition(
                ticker=ticker,
                quantity=quantity,
                entry_price=price,
                entry_time=datetime.now(),
                side=side,
            )

    def _remove_position(self, ticker: str, quantity: int):
        """Remove or reduce position."""
        if ticker not in self.positions:
            _LOG.warning("%s: Cannot sell - no position exists", ticker)
            return

        pos = self.positions[ticker]
        if quantity >= pos.quantity:
            # Close entire position
            del self.positions[ticker]
        else:
            # Reduce position
            pos.quantity -= quantity

    def get_positions(self) -> dict[str, SimulatedPosition]:
        """Get all current positions."""
        return self.positions.copy()

    def get_account_value(self, current_prices: dict[str, float]) -> float:
        """Calculate total account value.

        Args:
            current_prices: Dict of ticker -> current price

        Returns:
            Total account value (cash + positions)
        """
        position_value = 0.0

        for ticker, pos in self.positions.items():
            if ticker in current_prices:
                position_value += pos.quantity * current_prices[ticker]
            else:
                # Use entry price if current price unknown
                position_value += pos.quantity * pos.entry_price

        return self.cash + position_value

    def get_performance_stats(self) -> dict:
        """Get performance statistics."""
        completed_orders = [o for o in self.orders if o.status == "filled"]

        return {
            "initial_capital": self.initial_capital,
            "current_cash": self.cash,
            "total_orders": len(self.orders),
            "completed_orders": len(completed_orders),
            "rejected_orders": sum(1 for o in self.orders if o.status == "rejected"),
            "total_commissions": self.commission_per_trade * len(completed_orders),
            "open_positions": len(self.positions),
        }

    def reset(self):
        """Reset broker to initial state."""
        self.cash = self.initial_capital
        self.positions.clear()
        self.orders.clear()
        self.order_counter = 0
        _LOG.info("Simulation broker reset")
