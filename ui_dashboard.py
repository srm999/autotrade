"""Streamlit dashboard for multi-strategy trading bot.

Run with:
    streamlit run ui_dashboard.py

Access at:
    http://localhost:8501
"""
from __future__ import annotations

import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

# Add autotrade to path
sys.path.insert(0, str(Path(__file__).parent))

from autotrade.config import BotConfig
from main_multi_strategy import MultiStrategyBot

# Page config
st.set_page_config(
    page_title="AutoTrade Bot",
    page_icon="🤖",
    layout="wide",
)

# Initialize session state
if "bot" not in st.session_state:
    st.session_state.bot = None
    st.session_state.bot_thread = None
    st.session_state.is_running = False
    st.session_state.logs = []


def run_bot_background(bot):
    """Run bot in background thread."""
    try:
        bot.run()
    except Exception as e:
        st.session_state.logs.append(f"ERROR: {e}")
        st.session_state.is_running = False


def start_bot(capital: float, dry_run: bool):
    """Start the trading bot."""
    if st.session_state.is_running:
        return

    # Create configuration
    config = BotConfig.default(strategy="trend_following", capital=capital)

    # Create bot
    st.session_state.bot = MultiStrategyBot(config=config, dry_run=dry_run)
    st.session_state.logs.append(f"Bot initialized with ${capital:,.0f} capital")

    # Start bot in background thread
    st.session_state.bot_thread = threading.Thread(
        target=run_bot_background,
        args=(st.session_state.bot,),
        daemon=True,
    )
    st.session_state.bot_thread.start()
    st.session_state.is_running = True
    st.session_state.logs.append("Bot started!")


def stop_bot():
    """Stop the trading bot."""
    if not st.session_state.is_running:
        return

    st.session_state.is_running = False
    if st.session_state.bot:
        st.session_state.bot._shutdown()
    st.session_state.logs.append("Bot stopped")


# Main UI
st.title("🤖 AutoTrade - Multi-Strategy Trading Bot")
st.markdown("---")

# Sidebar - Controls
with st.sidebar:
    st.header("Bot Controls")

    # Capital input
    capital = st.number_input(
        "Trading Capital ($)",
        min_value=1000.0,
        max_value=1000000.0,
        value=10000.0,
        step=1000.0,
    )

    # Dry run toggle
    dry_run = st.checkbox("Dry Run (Simulation Mode)", value=True)

    # Start/Stop buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ Start", disabled=st.session_state.is_running, use_container_width=True):
            start_bot(capital, dry_run)
            st.rerun()

    with col2:
        if st.button("⏹️ Stop", disabled=not st.session_state.is_running, use_container_width=True):
            stop_bot()
            st.rerun()

    # Status indicator
    if st.session_state.is_running:
        st.success("🟢 Bot Running")
    else:
        st.error("🔴 Bot Stopped")

    st.markdown("---")

    # Mode indicator
    if dry_run:
        st.info("📊 **DRY RUN MODE**\n\nNo real trades will be executed")
    else:
        st.warning("⚠️ **LIVE TRADING MODE**\n\nReal money at risk!")

# Main content area
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "📈 Positions", "📜 Logs", "📋 Reports"])

with tab1:
    st.header("Trading Dashboard")

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)

    if st.session_state.bot:
        regime = st.session_state.bot.strategy_manager.current_regime
        active_strategies = st.session_state.bot.strategy_manager.get_active_strategies()
        position_count = len(st.session_state.bot._positions)

        with col1:
            st.metric("Market Regime", regime if regime else "Unknown")

        with col2:
            st.metric("Active Strategies", len(active_strategies))

        with col3:
            st.metric("Open Positions", position_count)

        with col4:
            if st.session_state.is_running:
                st.metric("Status", "Running", delta="Active")
            else:
                st.metric("Status", "Stopped", delta="Idle")

        # Active strategies
        if active_strategies:
            st.subheader("Active Strategies")
            for strategy_name in active_strategies:
                st.success(f"✅ {strategy_name}")
        else:
            st.info("No strategies active (cash preservation mode)")

    else:
        col1.metric("Market Regime", "—")
        col2.metric("Active Strategies", "—")
        col3.metric("Open Positions", "—")
        col4.metric("Status", "Not Started")

        st.info("👆 Click 'Start' in the sidebar to begin trading")

with tab2:
    st.header("Current Positions")

    if st.session_state.bot and st.session_state.bot._positions:
        positions_data = []
        for ticker, pos in st.session_state.bot._positions.items():
            # Try to get current price
            current_data = st.session_state.bot._fetch_price_data(ticker, days=1)
            if current_data is not None and len(current_data) > 0:
                current_price = current_data["close"].iloc[-1]
                pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                pnl_pct = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
            else:
                current_price = pos["entry_price"]
                pnl = 0
                pnl_pct = 0

            positions_data.append({
                "Ticker": ticker,
                "Strategy": pos["strategy"],
                "Direction": pos["direction"].upper(),
                "Quantity": pos["quantity"],
                "Entry Price": f"${pos['entry_price']:.2f}",
                "Current Price": f"${current_price:.2f}",
                "P&L": f"${pnl:.2f}",
                "P&L %": f"{pnl_pct:+.2f}%",
                "Days Held": (datetime.now() - pos["entry_date"]).days,
            })

        st.dataframe(positions_data, use_container_width=True)

    else:
        st.info("No open positions")

with tab3:
    st.header("Activity Log")

    # Auto-refresh checkbox
    auto_refresh = st.checkbox("Auto-refresh (every 5 seconds)", value=False)

    if auto_refresh:
        time.sleep(5)
        st.rerun()

    # Display logs
    log_container = st.container()
    with log_container:
        if st.session_state.logs:
            for log in st.session_state.logs[-50:]:  # Last 50 logs
                st.text(log)
        else:
            st.info("No activity yet")

    # Also show bot's log file if it exists
    log_file = Path("logs/trading_bot.log")
    if log_file.exists():
        st.subheader("Recent Bot Logs")
        with open(log_file) as f:
            lines = f.readlines()
            last_20 = "".join(lines[-20:])
            st.code(last_20, language="log")

with tab4:
    st.header("Daily Reports")

    # List available reports
    reports_dir = Path("reports")
    if reports_dir.exists():
        report_files = sorted(reports_dir.glob("daily_summary_*.txt"), reverse=True)

        if report_files:
            # Show most recent report
            st.subheader("Latest Report")
            selected_report = st.selectbox(
                "Select Report",
                options=report_files,
                format_func=lambda x: x.name,
            )

            if selected_report:
                with open(selected_report) as f:
                    report_content = f.read()
                st.text_area("Report Content", report_content, height=400)
        else:
            st.info("No reports generated yet")
    else:
        st.info("No reports directory found")

# Footer
st.markdown("---")
st.caption(f"AutoTrade v1.0 | Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
