"""Performance metrics calculation for backtest results."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    """Complete set of performance metrics for a trading strategy."""

    # Returns
    total_return: float = 0.0  # Total return as percentage
    annual_return: float = 0.0  # Annualized return (CAGR)
    monthly_return: float = 0.0  # Average monthly return

    # Risk-adjusted returns
    sharpe_ratio: float = 0.0  # Risk-adjusted return (assumes 0% risk-free rate)
    sortino_ratio: float = 0.0  # Downside risk-adjusted return
    calmar_ratio: float = 0.0  # Return / max drawdown

    # Risk metrics
    volatility: float = 0.0  # Annual volatility (std dev)
    max_drawdown: float = 0.0  # Maximum peak-to-trough decline
    max_drawdown_duration: int = 0  # Days in max drawdown

    # Trade statistics
    win_rate: float = 0.0  # Percentage of winning trades
    profit_factor: float = 0.0  # Gross profit / gross loss
    avg_win: float = 0.0  # Average winning trade
    avg_loss: float = 0.0  # Average losing trade
    avg_trade: float = 0.0  # Average trade return
    expectancy: float = 0.0  # Expected value per trade

    # Other
    num_trades: int = 0
    trading_days: int = 0

    @classmethod
    def from_equity_curve(
        cls,
        equity_curve: pd.Series,
        initial_capital: float,
        risk_free_rate: float = 0.0
    ) -> "PerformanceMetrics":
        """
        Calculate performance metrics from an equity curve.

        Args:
            equity_curve: Time series of portfolio values
            initial_capital: Starting capital
            risk_free_rate: Annual risk-free rate (default 0%)

        Returns:
            PerformanceMetrics object
        """
        if equity_curve.empty or len(equity_curve) < 2:
            return cls()

        # Calculate returns
        returns = equity_curve.pct_change().dropna()

        if returns.empty:
            return cls()

        # Total return
        final_value = equity_curve.iloc[-1]
        total_return = (final_value - initial_capital) / initial_capital * 100

        # Annualized return (CAGR)
        trading_days = len(equity_curve)
        years = trading_days / 252  # Assuming 252 trading days per year

        if years > 0 and final_value > 0 and initial_capital > 0:
            annual_return = (pow(final_value / initial_capital, 1 / years) - 1) * 100
        else:
            annual_return = 0.0

        # Monthly return
        monthly_return = annual_return / 12 if annual_return != 0 else 0.0

        # Volatility (annualized standard deviation)
        daily_vol = returns.std()
        annual_vol = daily_vol * math.sqrt(252) * 100  # Convert to percentage

        # Sharpe Ratio (annualized)
        if daily_vol > 0:
            daily_rf = (1 + risk_free_rate) ** (1/252) - 1
            excess_returns = returns - daily_rf
            sharpe = excess_returns.mean() / daily_vol * math.sqrt(252)
        else:
            sharpe = 0.0

        # Sortino Ratio (uses downside deviation only)
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0:
            downside_std = downside_returns.std()
            if downside_std > 0:
                sortino = returns.mean() / downside_std * math.sqrt(252)
            else:
                sortino = 0.0
        else:
            sortino = sharpe  # No downside, use Sharpe

        # Maximum Drawdown
        running_max = equity_curve.expanding().max()
        drawdown = (equity_curve - running_max) / running_max * 100
        max_dd = abs(drawdown.min())

        # Maximum Drawdown Duration
        is_in_dd = drawdown < 0
        dd_duration = 0
        current_duration = 0
        for in_dd in is_in_dd:
            if in_dd:
                current_duration += 1
                dd_duration = max(dd_duration, current_duration)
            else:
                current_duration = 0

        # Calmar Ratio
        if max_dd > 0:
            calmar = annual_return / max_dd
        else:
            calmar = 0.0

        return cls(
            total_return=total_return,
            annual_return=annual_return,
            monthly_return=monthly_return,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            volatility=annual_vol,
            max_drawdown=max_dd,
            max_drawdown_duration=dd_duration,
            trading_days=trading_days,
        )

    def to_dict(self) -> dict:
        """Convert metrics to dictionary."""
        return {
            'total_return': f"{self.total_return:.2f}%",
            'annual_return': f"{self.annual_return:.2f}%",
            'monthly_return': f"{self.monthly_return:.2f}%",
            'sharpe_ratio': f"{self.sharpe_ratio:.2f}",
            'sortino_ratio': f"{self.sortino_ratio:.2f}",
            'calmar_ratio': f"{self.calmar_ratio:.2f}",
            'volatility': f"{self.volatility:.2f}%",
            'max_drawdown': f"{self.max_drawdown:.2f}%",
            'max_drawdown_duration': f"{self.max_drawdown_duration} days",
            'win_rate': f"{self.win_rate * 100:.1f}%",
            'profit_factor': f"{self.profit_factor:.2f}",
            'avg_win': f"${self.avg_win:.2f}",
            'avg_loss': f"${self.avg_loss:.2f}",
            'num_trades': self.num_trades,
            'trading_days': self.trading_days,
        }

    def __str__(self) -> str:
        """Format metrics as readable string."""
        return f"""
Performance Metrics
===================
Returns:
  Total Return:        {self.total_return:>8.2f}%
  Annual Return (CAGR): {self.annual_return:>8.2f}%
  Monthly Return:       {self.monthly_return:>8.2f}%

Risk-Adjusted:
  Sharpe Ratio:        {self.sharpe_ratio:>8.2f}
  Sortino Ratio:       {self.sortino_ratio:>8.2f}
  Calmar Ratio:        {self.calmar_ratio:>8.2f}

Risk:
  Volatility (Annual): {self.volatility:>8.2f}%
  Max Drawdown:        {self.max_drawdown:>8.2f}%
  Max DD Duration:     {self.max_drawdown_duration:>8} days

Trade Statistics:
  Win Rate:            {self.win_rate * 100:>8.1f}%
  Profit Factor:       {self.profit_factor:>8.2f}
  Avg Win:             ${self.avg_win:>8.2f}
  Avg Loss:            ${self.avg_loss:>8.2f}
  Total Trades:        {self.num_trades:>8}
  Trading Days:        {self.trading_days:>8}
"""

    def is_acceptable(
        self,
        min_sharpe: float = 1.0,
        max_drawdown: float = 25.0,
        min_win_rate: float = 0.40
    ) -> bool:
        """
        Check if metrics meet minimum quality standards.

        Args:
            min_sharpe: Minimum Sharpe ratio (default 1.0)
            max_drawdown: Maximum acceptable drawdown % (default 25%)
            min_win_rate: Minimum win rate (default 40%)

        Returns:
            True if strategy meets all criteria
        """
        return (
            self.sharpe_ratio >= min_sharpe
            and self.max_drawdown <= max_drawdown
            and self.win_rate >= min_win_rate
        )
