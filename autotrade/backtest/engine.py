"""Backtesting engine with realistic transaction costs and slippage modeling."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from autotrade.backtest.metrics import PerformanceMetrics

_LOG = logging.getLogger(__name__)


@dataclass
class Trade:
    """Represents a single trade execution."""
    timestamp: datetime
    ticker: str
    side: str  # 'buy' or 'sell'
    quantity: int
    price: float
    commission: float
    slippage: float

    @property
    def total_cost(self) -> float:
        """Total cost including commission and slippage."""
        return self.commission + abs(self.slippage * self.quantity)

    @property
    def notional(self) -> float:
        """Notional value of trade."""
        return self.price * self.quantity


@dataclass
class Position:
    """Tracks open position for a ticker."""
    ticker: str
    quantity: int = 0
    avg_entry_price: float = 0.0
    entry_timestamp: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.quantity > 0

    @property
    def market_value(self, current_price: float) -> float:
        return self.quantity * current_price

    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L."""
        if self.quantity == 0:
            return 0.0
        return (current_price - self.avg_entry_price) * self.quantity


@dataclass
class BacktestConfig:
    """Configuration for backtest execution."""
    initial_capital: float = 10_000.0
    commission_pct: float = 0.0  # Schwab is $0 commission
    commission_fixed: float = 0.0  # No fixed commission
    slippage_pct: float = 0.05  # 5 basis points = 0.05%
    sec_fee_rate: float = 0.0000278  # SEC fee per dollar sold
    taf_fee_per_share: float = 0.000166  # TAF fee (capped at $7.27)
    use_bid_ask_slippage: bool = False  # If True, use bid-ask spread for slippage
    max_positions: int = 5
    position_size_pct: float = 20.0  # Max 20% per position

    def total_transaction_cost(self, notional: float, shares: int, side: str) -> float:
        """Calculate total transaction cost for a trade.

        Args:
            notional: Dollar value of trade
            shares: Number of shares
            side: 'buy' or 'sell'

        Returns:
            Total cost in dollars
        """
        # Commission (usually $0 for Schwab)
        commission = self.commission_fixed + (notional * self.commission_pct / 100)

        # Slippage (applies to both buy and sell)
        slippage = notional * (self.slippage_pct / 100)

        # SEC and TAF fees (only on sells)
        regulatory_fees = 0.0
        if side == 'sell':
            sec_fee = notional * self.sec_fee_rate
            taf_fee = min(shares * self.taf_fee_per_share, 7.27)  # Capped at $7.27
            regulatory_fees = sec_fee + taf_fee

        return commission + slippage + regulatory_fees


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    daily_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    metrics: PerformanceMetrics | None = None

    config: BacktestConfig | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None

    def summary(self) -> dict[str, Any]:
        """Generate summary statistics."""
        if self.metrics is None:
            return {}

        total_trades = len(self.trades)
        total_costs = sum(t.total_cost for t in self.trades)

        return {
            'total_return': self.metrics.total_return,
            'annual_return': self.metrics.annual_return,
            'sharpe_ratio': self.metrics.sharpe_ratio,
            'sortino_ratio': self.metrics.sortino_ratio,
            'max_drawdown': self.metrics.max_drawdown,
            'win_rate': self.metrics.win_rate,
            'profit_factor': self.metrics.profit_factor,
            'total_trades': total_trades,
            'total_costs': total_costs,
            'avg_cost_per_trade': total_costs / total_trades if total_trades > 0 else 0,
            'start_date': self.start_date,
            'end_date': self.end_date,
        }


class BacktestEngine:
    """
    Backtesting engine that simulates strategy execution on historical data.

    Features:
    - Realistic transaction costs (slippage, SEC fees, TAF fees)
    - Position sizing and portfolio constraints
    - Multiple simultaneous positions
    - Daily EOD execution model
    - Performance metrics calculation
    """

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self._cash = config.initial_capital
        self._positions: dict[str, Position] = {}
        self._trades: list[Trade] = []
        self._equity_history: list[tuple[datetime, float]] = []
        self._daily_returns: list[float] = []

    def reset(self) -> None:
        """Reset backtest state."""
        self._cash = self.config.initial_capital
        self._positions.clear()
        self._trades.clear()
        self._equity_history.clear()
        self._daily_returns.clear()

    @property
    def portfolio_value(self) -> float:
        """Current portfolio value (cash + positions)."""
        return self._cash

    @property
    def positions_value(self, prices: dict[str, float]) -> float:
        """Market value of all positions."""
        return sum(
            pos.quantity * prices.get(pos.ticker, 0.0)
            for pos in self._positions.values()
            if pos.is_open
        )

    def can_open_position(self) -> bool:
        """Check if we can open a new position."""
        open_positions = sum(1 for pos in self._positions.values() if pos.is_open)
        return open_positions < self.config.max_positions

    def calculate_position_size(
        self,
        ticker: str,
        price: float,
        risk_pct: float = 2.0,
        atr: float | None = None,
        atr_multiplier: float = 2.0
    ) -> int:
        """
        Calculate position size using volatility-based sizing.

        Args:
            ticker: Stock ticker
            price: Current price
            risk_pct: Percentage of capital to risk (default 2%)
            atr: Average True Range (optional, for volatility adjustment)
            atr_multiplier: Multiplier for ATR-based stop (default 2x)

        Returns:
            Number of shares to buy
        """
        # Risk amount in dollars
        risk_amount = self.portfolio_value * (risk_pct / 100)

        # If ATR provided, use volatility-based sizing
        if atr and atr > 0:
            # Stop loss distance = atr_multiplier * ATR
            stop_distance = atr * atr_multiplier
            shares = int(risk_amount / stop_distance)
        else:
            # Simple fixed percentage sizing
            max_position_value = self.portfolio_value * (self.config.position_size_pct / 100)
            shares = int(max_position_value / price)

        # Ensure we have enough cash
        notional = shares * price
        if notional > self._cash:
            shares = int(self._cash / price)

        return max(0, shares)

    def execute_trade(
        self,
        timestamp: datetime,
        ticker: str,
        side: str,
        quantity: int,
        price: float,
    ) -> Trade | None:
        """
        Execute a trade with realistic costs.

        Args:
            timestamp: Execution time
            ticker: Stock ticker
            side: 'buy' or 'sell'
            quantity: Number of shares
            price: Execution price

        Returns:
            Trade object if successful, None otherwise
        """
        if quantity <= 0:
            return None

        notional = quantity * price

        # Calculate transaction costs
        total_cost = self.config.total_transaction_cost(notional, quantity, side)

        # Check if we have enough cash for buy
        if side == 'buy':
            if notional + total_cost > self._cash:
                _LOG.warning(
                    "Insufficient cash for trade: need $%.2f, have $%.2f",
                    notional + total_cost,
                    self._cash
                )
                return None

            # Deduct cash
            self._cash -= (notional + total_cost)

            # Update position
            if ticker not in self._positions:
                self._positions[ticker] = Position(ticker=ticker)

            pos = self._positions[ticker]
            total_cost_basis = pos.avg_entry_price * pos.quantity + notional
            pos.quantity += quantity
            pos.avg_entry_price = total_cost_basis / pos.quantity

            if pos.entry_timestamp is None:
                pos.entry_timestamp = timestamp

        elif side == 'sell':
            # Check if we have the position
            if ticker not in self._positions or self._positions[ticker].quantity < quantity:
                _LOG.warning(
                    "Insufficient shares to sell: ticker=%s, have=%d, trying to sell=%d",
                    ticker,
                    self._positions.get(ticker, Position(ticker=ticker)).quantity,
                    quantity
                )
                return None

            # Add cash (minus costs)
            self._cash += (notional - total_cost)

            # Update position
            pos = self._positions[ticker]
            pos.quantity -= quantity

            if pos.quantity == 0:
                pos.avg_entry_price = 0.0
                pos.entry_timestamp = None

        # Create trade record
        trade = Trade(
            timestamp=timestamp,
            ticker=ticker,
            side=side,
            quantity=quantity,
            price=price,
            commission=self.config.commission_fixed + (notional * self.config.commission_pct / 100),
            slippage=notional * (self.config.slippage_pct / 100)
        )

        self._trades.append(trade)

        _LOG.debug(
            "Executed trade: %s %s x%d @ %.2f (cost=%.2f)",
            side,
            ticker,
            quantity,
            price,
            total_cost
        )

        return trade

    def update_equity(self, timestamp: datetime, prices: dict[str, float]) -> float:
        """
        Update equity curve with current market prices.

        Args:
            timestamp: Current timestamp
            prices: Dictionary of ticker -> current price

        Returns:
            Current portfolio value
        """
        positions_value = sum(
            pos.quantity * prices.get(pos.ticker, pos.avg_entry_price)
            for pos in self._positions.values()
            if pos.is_open
        )

        portfolio_value = self._cash + positions_value
        self._equity_history.append((timestamp, portfolio_value))

        return portfolio_value

    def calculate_daily_return(self) -> float:
        """Calculate daily return from last two equity points."""
        if len(self._equity_history) < 2:
            return 0.0

        prev_value = self._equity_history[-2][1]
        curr_value = self._equity_history[-1][1]

        if prev_value == 0:
            return 0.0

        daily_return = (curr_value - prev_value) / prev_value
        self._daily_returns.append(daily_return)

        return daily_return

    def get_results(self) -> BacktestResult:
        """
        Generate backtest results with performance metrics.

        Returns:
            BacktestResult with complete metrics
        """
        # Convert equity history to pandas Series
        if self._equity_history:
            timestamps, values = zip(*self._equity_history)
            equity_curve = pd.Series(values, index=pd.DatetimeIndex(timestamps))
        else:
            equity_curve = pd.Series(dtype=float)

        # Daily returns series
        daily_returns = pd.Series(self._daily_returns)

        # Calculate performance metrics
        metrics = PerformanceMetrics.from_equity_curve(
            equity_curve,
            initial_capital=self.config.initial_capital
        )

        # Add trade statistics to metrics
        if self._trades:
            # Calculate win rate and profit factor from closed trades
            closed_pnls = self._calculate_closed_trade_pnls()
            if closed_pnls:
                wins = [pnl for pnl in closed_pnls if pnl > 0]
                losses = [pnl for pnl in closed_pnls if pnl < 0]

                metrics.win_rate = len(wins) / len(closed_pnls) if closed_pnls else 0.0

                total_wins = sum(wins) if wins else 0.0
                total_losses = abs(sum(losses)) if losses else 0.0
                metrics.profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

        start_date = self._equity_history[0][0] if self._equity_history else None
        end_date = self._equity_history[-1][0] if self._equity_history else None

        return BacktestResult(
            trades=self._trades.copy(),
            equity_curve=equity_curve,
            daily_returns=daily_returns,
            metrics=metrics,
            config=self.config,
            start_date=start_date,
            end_date=end_date
        )

    def _calculate_closed_trade_pnls(self) -> list[float]:
        """Calculate P&L for all closed positions (buy followed by sell)."""
        pnls = []
        position_tracker: dict[str, list[tuple[float, int]]] = {}  # ticker -> [(price, quantity)]

        for trade in self._trades:
            if trade.side == 'buy':
                if trade.ticker not in position_tracker:
                    position_tracker[trade.ticker] = []
                position_tracker[trade.ticker].append((trade.price, trade.quantity))

            elif trade.side == 'sell':
                if trade.ticker in position_tracker and position_tracker[trade.ticker]:
                    # FIFO: match with oldest buy
                    remaining_sell_qty = trade.quantity

                    while remaining_sell_qty > 0 and position_tracker[trade.ticker]:
                        buy_price, buy_qty = position_tracker[trade.ticker][0]

                        if buy_qty <= remaining_sell_qty:
                            # Close entire buy position
                            pnl = (trade.price - buy_price) * buy_qty - trade.total_cost
                            pnls.append(pnl)
                            remaining_sell_qty -= buy_qty
                            position_tracker[trade.ticker].pop(0)
                        else:
                            # Partial close
                            pnl = (trade.price - buy_price) * remaining_sell_qty - trade.total_cost
                            pnls.append(pnl)
                            position_tracker[trade.ticker][0] = (buy_price, buy_qty - remaining_sell_qty)
                            remaining_sell_qty = 0

        return pnls
