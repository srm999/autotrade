"""Daily reporting utilities for summarizing trading loop activity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from autotrade.config import BotConfig
from autotrade.data.market import Quote
from autotrade.strategy.base import Signal
from autotrade.strategy.base import StrategyDiagnostics


@dataclass(slots=True)
class QuoteSnapshot:
    as_of: datetime
    price: float
    metrics: dict[str, float] | None


@dataclass(slots=True)
class SignalSnapshot:
    timestamp: datetime
    ticker: str
    side: str
    reason: str
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class ErrorSnapshot:
    timestamp: datetime
    ticker: str
    message: str


@dataclass(slots=True)
class PortfolioSnapshot:
    timestamp: datetime
    market_value: float
    cash_available: float
    cash_withdrawal: float


class DailySummaryReporter:
    """Collects intra-day facts and renders a plain-text summary at session end."""

    def __init__(
        self,
        config: BotConfig,
        *,
        output_dir: str | Path = "data/reports",
    ) -> None:
        self._config = config
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._start_time: datetime | None = None
        self._end_time: datetime | None = None
        self._quotes: dict[str, QuoteSnapshot] = {}
        self._signals: list[SignalSnapshot] = []
        self._errors: list[ErrorSnapshot] = []
        self._flatten_events: list[datetime] = []
        self._regime_history: list[tuple[datetime, str | None, str | None]] = []
        self._last_diagnostics: StrategyDiagnostics | None = None
        self._portfolio_history: list[PortfolioSnapshot] = []

    def record_quote(self, quote: Quote, diagnostics: StrategyDiagnostics | None) -> None:
        self._register_start(quote.as_of)
        if diagnostics:
            self._update_regime_history(diagnostics, quote.as_of)
            self._last_diagnostics = diagnostics
        metrics = diagnostics.latest_metrics.get(quote.ticker) if diagnostics else None
        self._quotes[quote.ticker] = QuoteSnapshot(as_of=quote.as_of, price=quote.price, metrics=metrics)

    def record_signal(self, signal: Signal, diagnostics: StrategyDiagnostics | None, *, timestamp: datetime) -> None:
        self._register_start(timestamp)
        if diagnostics:
            self._update_regime_history(diagnostics, timestamp)
            self._last_diagnostics = diagnostics
        reason = ""
        if signal.metadata and isinstance(signal.metadata, dict):
            reason = str(signal.metadata.get("reason", ""))
        snapshot = SignalSnapshot(
            timestamp=timestamp,
            ticker=signal.ticker,
            side=signal.side,
            reason=reason or "signal",
            metadata=signal.metadata,
        )
        self._signals.append(snapshot)

    def record_portfolio(self, *, timestamp: datetime, profile: dict[str, Any]) -> None:
        self._register_start(timestamp)
        market_value = float(profile.get("market_value", 0.0) or 0.0)
        cash_available = float(profile.get("cash_available_for_trading", 0.0) or 0.0)
        cash_withdrawal = float(profile.get("cash_available_for_withdrawal", 0.0) or 0.0)
        self._portfolio_history.append(
            PortfolioSnapshot(
                timestamp=timestamp,
                market_value=market_value,
                cash_available=cash_available,
                cash_withdrawal=cash_withdrawal,
            )
        )

    def record_flatten(self, *, timestamp: datetime, diagnostics: StrategyDiagnostics | None) -> None:
        self._register_start(timestamp)
        if diagnostics:
            self._update_regime_history(diagnostics, timestamp)
            self._last_diagnostics = diagnostics
        self._flatten_events.append(timestamp)

    def record_error(self, *, ticker: str, error: Exception, timestamp: datetime) -> None:
        self._register_start(timestamp)
        message = f"{error.__class__.__name__}: {error}"
        self._errors.append(ErrorSnapshot(timestamp=timestamp, ticker=ticker, message=message))

    def finalize(self, *, end_time: datetime, reason: str) -> str:
        self._end_time = end_time
        if not self._start_time:
            self._start_time = end_time
        session_date = self._start_time.date()
        header = f"Daily Summary {session_date.isoformat()} (reason: {reason})"
        lines: list[str] = [header]
        start_str = self._format_dt(self._start_time)
        end_str = self._format_dt(self._end_time)
        lines.append(f"- Session window: start {start_str}, end {end_str}")

        lines.append(self._format_regime_line())
        lines.extend(self._format_quote_lines())
        lines.append(self._format_signal_line())
        lines.append(self._format_flatten_line())
        extra_line = self._format_extras_line()
        if extra_line:
            lines.append(extra_line)
        lines.append(self._format_portfolio_line())
        lines.append(self._format_error_line())

        summary = "\n".join(line for line in lines if line)
        output_path = self._output_dir / f"{session_date.isoformat()}.txt"
        output_path.write_text(summary, encoding="utf-8")
        return summary

    def _register_start(self, timestamp: datetime) -> None:
        if not self._start_time:
            self._start_time = timestamp

    def _update_regime_history(self, diagnostics: StrategyDiagnostics, timestamp: datetime) -> None:
        regime = diagnostics.regime
        target = diagnostics.target_ticker
        if not self._regime_history:
            self._regime_history.append((timestamp, regime, target))
            return
        last_ts, last_regime, last_target = self._regime_history[-1]
        if regime == last_regime and target == last_target:
            return
        if last_ts == timestamp and regime == last_regime and target == last_target:
            return
        self._regime_history.append((timestamp, regime, target))

    def _format_regime_line(self) -> str:
        if not self._regime_history and not self._last_diagnostics:
            return "- Regime: unavailable"
        regimes = self._regime_history or [
            (
                self._last_diagnostics.timestamp if self._last_diagnostics else self._start_time,
                self._last_diagnostics.regime if self._last_diagnostics else None,
                self._last_diagnostics.target_ticker if self._last_diagnostics else None,
            )
        ]
        parts = []
        for ts, regime, target in regimes:
            tag = regime or "neutral"
            tgt = target or "-"
            time_str = self._format_time(ts)
            parts.append(f"{time_str} {tag}→{tgt}")
        joined = "; ".join(parts)
        return f"- Regime timeline: {joined}"

    def _format_quote_lines(self) -> list[str]:
        lines: list[str] = []
        params = self._config.strategy.params
        for ticker in self._config.strategy.tickers:
            snapshot = self._quotes.get(ticker)
            if not snapshot:
                lines.append(f"- {ticker}: no intraday quotes captured")
                continue
            metrics = snapshot.metrics or {}
            z_str = self._format_metric(metrics.get("z_score"))
            sma_fast = self._format_metric(metrics.get("sma_fast"))
            sma_slow = self._format_metric(metrics.get("sma_slow"))
            price = f"{snapshot.price:.2f}"
            time_str = self._format_time(snapshot.as_of)
            lines.append(
                f"- {ticker}: price {price} @ {time_str}, z={z_str} (entry ±{params.entry_zscore:.2f}, exit {params.exit_zscore:.2f}); "
                f"sma_fast={sma_fast}, sma_slow={sma_slow}"
            )
        return lines

    def _format_signal_line(self) -> str:
        if not self._signals:
            if self._last_diagnostics and any(self._quotes.values()):
                ticker_metrics = []
                for ticker, snapshot in self._quotes.items():
                    metrics = snapshot.metrics or {}
                    z_str = self._format_metric(metrics.get("z_score"))
                    ticker_metrics.append(f"{ticker} z={z_str}")
                joined = ", ".join(ticker_metrics)
                return f"- Signals: none (latest indicators: {joined})"
            return "- Signals: none"
        parts = []
        for signal in self._signals:
            time_str = self._format_time(signal.timestamp)
            reason = signal.reason
            parts.append(f"{time_str} {signal.side.upper()} {signal.ticker} ({reason})")
        return "- Signals: " + "; ".join(parts)

    def _format_flatten_line(self) -> str:
        if not self._flatten_events:
            return "- Flatten events: none"
        parts = [self._format_time(ts) for ts in self._flatten_events]
        return "- Flatten events: " + ", ".join(parts)

    def _format_portfolio_line(self) -> str:
        if not self._portfolio_history:
            return "- Portfolio balances: unavailable"
        first = self._portfolio_history[0]
        last = self._portfolio_history[-1]
        start_cash = self._format_currency(first.cash_available)
        end_cash = self._format_currency(last.cash_available)
        start_mv = self._format_currency(first.market_value)
        end_mv = self._format_currency(last.market_value)
        line = (
            f"- Portfolio balances: cash start {start_cash}, end {end_cash}; "
            f"market value start {start_mv}, end {end_mv}"
        )
        if last.cash_withdrawal:
            line += f"; cash withdrawable {self._format_currency(last.cash_withdrawal)}"
        return line

    def _format_error_line(self) -> str:
        if not self._errors:
            return "- Errors: none"
        parts = [
            f"{self._format_time(err.timestamp)} {err.ticker} -> {err.message}"
            for err in self._errors
        ]
        return "- Errors: " + "; ".join(parts)

    def _format_extras_line(self) -> str:
        diagnostics = self._last_diagnostics
        if not diagnostics or not diagnostics.extras:
            return ""
        parts = []
        for key, value in diagnostics.extras.items():
            if value in (None, "", []):
                continue
            parts.append(f"{key}={value}")
        if not parts:
            return ""
        return "- Strategy state: " + ", ".join(parts)

    @staticmethod
    def _format_currency(value: float) -> str:
        return f"${value:,.2f}"

    @staticmethod
    def _format_dt(ts: datetime | None) -> str:
        if not ts:
            return "n/a"
        return ts.replace(microsecond=0).isoformat()

    @staticmethod
    def _format_time(ts: datetime | None) -> str:
        if not ts:
            return "n/a"
        return ts.astimezone().strftime("%H:%M:%S")

    @staticmethod
    def _format_metric(value: float | None) -> str:
        if value is None:
            return "n/a"
        return f"{value:.3f}"


class PerformanceReporter:
    """Performance reporting for multi-strategy bot."""

    def __init__(self, reports_dir: str | Path = "reports"):
        """Initialize performance reporter.

        Args:
            reports_dir: Directory to save daily reports
        """
        self._trades = []
        self._daily_pnl = []
        self._regime_changes = []
        self._signals_generated = []
        self._errors = []
        self._session_start = None
        self._reports_dir = Path(reports_dir)
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    def record_trade(self, ticker: str, action: str, quantity: int, price: float,
                    strategy: str, pnl: float = None):
        """Record a completed trade.

        Args:
            ticker: Stock ticker
            action: "buy" or "sell"
            quantity: Number of shares
            price: Execution price
            strategy: Strategy name
            pnl: Profit/loss (for exits only)
        """
        trade = {
            "ticker": ticker,
            "action": action,
            "quantity": quantity,
            "price": price,
            "strategy": strategy,
            "pnl": pnl,
            "timestamp": datetime.now(),
        }
        self._trades.append(trade)

        if self._session_start is None:
            self._session_start = datetime.now()

    def record_regime_change(self, regime: str, active_strategies: list[str]):
        """Record a market regime change.

        Args:
            regime: Market regime description
            active_strategies: List of activated strategy names
        """
        self._regime_changes.append({
            "timestamp": datetime.now(),
            "regime": regime,
            "active_strategies": active_strategies,
        })

    def record_signal(self, ticker: str, signal_type: str, strategy: str,
                     confidence: float, executed: bool):
        """Record a trading signal.

        Args:
            ticker: Stock ticker
            signal_type: Signal type (entry/exit)
            strategy: Strategy that generated signal
            confidence: Signal confidence (0-1)
            executed: Whether signal was executed
        """
        self._signals_generated.append({
            "timestamp": datetime.now(),
            "ticker": ticker,
            "signal_type": signal_type,
            "strategy": strategy,
            "confidence": confidence,
            "executed": executed,
        })

    def record_error(self, error: Exception, context: str = ""):
        """Record an error.

        Args:
            error: Exception that occurred
            context: Context/description of where error occurred
        """
        self._errors.append({
            "timestamp": datetime.now(),
            "error": str(error),
            "type": error.__class__.__name__,
            "context": context,
        })

    def record_daily_pnl(self, pnl: float):
        """Record daily profit/loss."""
        self._daily_pnl.append({
            "date": datetime.now().date(),
            "pnl": pnl,
        })

    def get_summary(self) -> dict:
        """Get performance summary."""
        if not self._trades:
            return {
                "total_trades": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
            }

        total_pnl = sum(t["pnl"] for t in self._trades if t["pnl"] is not None)
        winning_trades = sum(1 for t in self._trades if t["pnl"] and t["pnl"] > 0)
        completed_trades = sum(1 for t in self._trades if t["pnl"] is not None)

        win_rate = (winning_trades / completed_trades * 100) if completed_trades > 0 else 0.0

        return {
            "total_trades": len(self._trades),
            "completed_trades": completed_trades,
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "avg_pnl": total_pnl / completed_trades if completed_trades > 0 else 0.0,
        }

    def generate_daily_summary(self, date: datetime.date = None) -> str:
        """Generate comprehensive daily summary report.

        Args:
            date: Date for report (defaults to today)

        Returns:
            Formatted summary report
        """
        if date is None:
            date = datetime.now().date()

        # Filter trades for the day
        day_trades = [t for t in self._trades
                     if t["timestamp"].date() == date]

        # Filter signals for the day
        day_signals = [s for s in self._signals_generated
                      if s["timestamp"].date() == date]

        # Filter regime changes for the day
        day_regimes = [r for r in self._regime_changes
                      if r["timestamp"].date() == date]

        # Filter errors for the day
        day_errors = [e for e in self._errors
                     if e["timestamp"].date() == date]

        # Build report
        lines = []
        lines.append("=" * 80)
        lines.append(f"AUTOTRADE - DAILY TRADING SUMMARY")
        lines.append(f"Date: {date.strftime('%A, %B %d, %Y')}")
        lines.append("=" * 80)
        lines.append("")

        # Session info
        if self._session_start:
            lines.append("SESSION INFO")
            lines.append("-" * 80)
            lines.append(f"Session started: {self._session_start.strftime('%H:%M:%S')}")
            lines.append(f"Report generated: {datetime.now().strftime('%H:%M:%S')}")
            lines.append("")

        # Market regime changes
        lines.append("MARKET REGIME CHANGES")
        lines.append("-" * 80)
        if day_regimes:
            for regime in day_regimes:
                time_str = regime["timestamp"].strftime('%H:%M:%S')
                strategies = ", ".join(regime["active_strategies"]) if regime["active_strategies"] else "None (cash preservation)"
                lines.append(f"[{time_str}] {regime['regime']}")
                lines.append(f"           Active strategies: {strategies}")
        else:
            lines.append("No regime changes recorded")
        lines.append("")

        # Trading activity
        lines.append("TRADING ACTIVITY")
        lines.append("-" * 80)

        if day_trades:
            # Group by ticker
            by_ticker = {}
            for trade in day_trades:
                ticker = trade["ticker"]
                if ticker not in by_ticker:
                    by_ticker[ticker] = []
                by_ticker[ticker].append(trade)

            for ticker, trades in by_ticker.items():
                lines.append(f"\n{ticker}:")
                for trade in trades:
                    time_str = trade["timestamp"].strftime('%H:%M:%S')
                    action_str = trade["action"].upper()
                    qty = trade["quantity"]
                    price = trade["price"]
                    strategy = trade["strategy"]

                    line = f"  [{time_str}] {action_str} {qty:,} shares @ ${price:.2f} ({strategy})"

                    if trade["pnl"] is not None:
                        pnl_sign = "+" if trade["pnl"] >= 0 else ""
                        line += f" - P&L: {pnl_sign}${trade['pnl']:.2f}"

                    lines.append(line)

            # Summary stats
            lines.append("")
            total_buys = sum(1 for t in day_trades if t["action"] == "buy")
            total_sells = sum(1 for t in day_trades if t["action"] == "sell")
            total_pnl = sum(t["pnl"] for t in day_trades if t["pnl"] is not None)

            lines.append(f"Total trades: {len(day_trades)} ({total_buys} buys, {total_sells} sells)")
            if total_pnl != 0:
                pnl_sign = "+" if total_pnl >= 0 else ""
                lines.append(f"Total P&L: {pnl_sign}${total_pnl:.2f}")
        else:
            lines.append("No trades executed today")

        lines.append("")

        # Signals generated
        lines.append("SIGNALS GENERATED")
        lines.append("-" * 80)

        if day_signals:
            executed_signals = [s for s in day_signals if s["executed"]]
            ignored_signals = [s for s in day_signals if not s["executed"]]

            lines.append(f"Total signals: {len(day_signals)}")
            lines.append(f"Executed: {len(executed_signals)}")
            lines.append(f"Ignored: {len(ignored_signals)}")
            lines.append("")

            # Group by strategy
            by_strategy = {}
            for signal in day_signals:
                strategy = signal["strategy"]
                if strategy not in by_strategy:
                    by_strategy[strategy] = []
                by_strategy[strategy].append(signal)

            for strategy, signals in by_strategy.items():
                lines.append(f"\n{strategy}:")
                for signal in signals[:10]:  # Max 10 per strategy
                    time_str = signal["timestamp"].strftime('%H:%M:%S')
                    ticker = signal["ticker"]
                    signal_type = signal["signal_type"].upper()
                    confidence = signal["confidence"] * 100
                    executed = "✓ EXECUTED" if signal["executed"] else "✗ Ignored"
                    lines.append(f"  [{time_str}] {ticker} - {signal_type} (confidence: {confidence:.0f}%) - {executed}")
        else:
            lines.append("No signals generated today")

        lines.append("")

        # Performance summary
        lines.append("PERFORMANCE SUMMARY")
        lines.append("-" * 80)

        summary = self.get_summary()
        lines.append(f"Total trades (all-time): {summary['total_trades']}")
        lines.append(f"Completed trades: {summary['completed_trades']}")
        lines.append(f"Win rate: {summary['win_rate']:.1f}%")

        if summary['total_pnl'] != 0:
            pnl_sign = "+" if summary['total_pnl'] >= 0 else ""
            lines.append(f"Total P&L (all-time): {pnl_sign}${summary['total_pnl']:.2f}")
            lines.append(f"Average P&L per trade: {pnl_sign}${summary['avg_pnl']:.2f}")

        lines.append("")

        # Errors
        if day_errors:
            lines.append("ERRORS")
            lines.append("-" * 80)
            for error in day_errors:
                time_str = error["timestamp"].strftime('%H:%M:%S')
                error_type = error["type"]
                error_msg = error["error"]
                context = f" ({error['context']})" if error['context'] else ""
                lines.append(f"[{time_str}] {error_type}{context}: {error_msg}")
            lines.append("")

        # Footer
        lines.append("=" * 80)
        lines.append("End of Report")
        lines.append("=" * 80)

        report = "\n".join(lines)

        # Save to file
        filename = f"daily_summary_{date.isoformat()}.txt"
        filepath = self._reports_dir / filename
        filepath.write_text(report, encoding="utf-8")

        return report

    def reset_daily_stats(self):
        """Reset daily statistics (call at start of new trading day)."""
        self._session_start = datetime.now()
        # Keep cumulative stats but could add daily filtering if needed
