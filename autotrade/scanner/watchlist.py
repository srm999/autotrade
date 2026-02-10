"""Watchlist management for tracking potential trades.

Supports:
- Static watchlists (user-defined)
- Dynamic watchlists (from screeners)
- Per-strategy watchlists
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_LOG = logging.getLogger(__name__)


@dataclass
class Watchlist:
    """A watchlist of ticker symbols."""

    name: str
    tickers: set[str] = field(default_factory=set)
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    is_dynamic: bool = False  # Dynamic watchlists auto-update from screeners

    def add_ticker(self, ticker: str) -> None:
        """Add ticker to watchlist."""
        ticker = ticker.upper()
        if ticker not in self.tickers:
            self.tickers.add(ticker)
            self.updated_at = datetime.now()
            _LOG.info("Added %s to watchlist '%s'", ticker, self.name)

    def remove_ticker(self, ticker: str) -> None:
        """Remove ticker from watchlist."""
        ticker = ticker.upper()
        if ticker in self.tickers:
            self.tickers.remove(ticker)
            self.updated_at = datetime.now()
            _LOG.info("Removed %s from watchlist '%s'", ticker, self.name)

    def contains(self, ticker: str) -> bool:
        """Check if ticker is in watchlist."""
        return ticker.upper() in self.tickers

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "tickers": sorted(list(self.tickers)),
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_dynamic": self.is_dynamic,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Watchlist:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            tickers=set(data["tickers"]),
            description=data.get("description", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            is_dynamic=data.get("is_dynamic", False),
        )


class WatchlistManager:
    """Manages multiple watchlists."""

    def __init__(self, data_dir: Path | None = None):
        """
        Initialize watchlist manager.

        Args:
            data_dir: Directory for persisting watchlists (default: data/watchlists)
        """
        self.data_dir = data_dir or Path("data/watchlists")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._watchlists: dict[str, Watchlist] = {}
        self._load_watchlists()

    def create_watchlist(
        self,
        name: str,
        tickers: list[str] | None = None,
        description: str = "",
        is_dynamic: bool = False,
    ) -> Watchlist:
        """
        Create a new watchlist.

        Args:
            name: Watchlist name
            tickers: Initial list of tickers
            description: Watchlist description
            is_dynamic: Whether watchlist auto-updates from screeners

        Returns:
            Created Watchlist
        """
        if name in self._watchlists:
            _LOG.warning("Watchlist '%s' already exists", name)
            return self._watchlists[name]

        watchlist = Watchlist(
            name=name,
            tickers=set(ticker.upper() for ticker in tickers) if tickers else set(),
            description=description,
            is_dynamic=is_dynamic,
        )

        self._watchlists[name] = watchlist
        self._save_watchlist(watchlist)

        _LOG.info("Created watchlist '%s' with %d tickers", name, len(watchlist.tickers))

        return watchlist

    def get_watchlist(self, name: str) -> Watchlist | None:
        """Get watchlist by name."""
        return self._watchlists.get(name)

    def get_all_watchlists(self) -> list[Watchlist]:
        """Get all watchlists."""
        return list(self._watchlists.values())

    def get_combined_tickers(self, watchlist_names: list[str] | None = None) -> set[str]:
        """
        Get combined set of tickers from multiple watchlists.

        Args:
            watchlist_names: Names of watchlists to combine (all if None)

        Returns:
            Set of unique tickers
        """
        if watchlist_names is None:
            watchlist_names = list(self._watchlists.keys())

        combined = set()
        for name in watchlist_names:
            watchlist = self._watchlists.get(name)
            if watchlist:
                combined.update(watchlist.tickers)

        return combined

    def update_dynamic_watchlist(self, name: str, tickers: list[str]) -> None:
        """
        Update a dynamic watchlist with new tickers from screener.

        Args:
            name: Watchlist name
            tickers: New list of tickers
        """
        watchlist = self._watchlists.get(name)
        if not watchlist:
            # Create if doesn't exist
            watchlist = self.create_watchlist(name, tickers, is_dynamic=True)
            return

        if not watchlist.is_dynamic:
            _LOG.warning("Cannot update non-dynamic watchlist '%s'", name)
            return

        # Replace tickers
        watchlist.tickers = set(ticker.upper() for ticker in tickers)
        watchlist.updated_at = datetime.now()

        self._save_watchlist(watchlist)

        _LOG.info(
            "Updated dynamic watchlist '%s' with %d tickers",
            name,
            len(watchlist.tickers),
        )

    def delete_watchlist(self, name: str) -> bool:
        """Delete a watchlist."""
        if name not in self._watchlists:
            return False

        del self._watchlists[name]

        # Delete file
        file_path = self.data_dir / f"{name}.json"
        if file_path.exists():
            file_path.unlink()

        _LOG.info("Deleted watchlist '%s'", name)
        return True

    def _save_watchlist(self, watchlist: Watchlist) -> None:
        """Save watchlist to disk."""
        file_path = self.data_dir / f"{watchlist.name}.json"

        with open(file_path, "w") as f:
            json.dump(watchlist.to_dict(), f, indent=2)

    def _load_watchlists(self) -> None:
        """Load all watchlists from disk."""
        if not self.data_dir.exists():
            return

        for file_path in self.data_dir.glob("*.json"):
            try:
                with open(file_path) as f:
                    data = json.load(f)
                    watchlist = Watchlist.from_dict(data)
                    self._watchlists[watchlist.name] = watchlist
                    _LOG.debug(
                        "Loaded watchlist '%s' with %d tickers",
                        watchlist.name,
                        len(watchlist.tickers),
                    )
            except Exception as e:
                _LOG.error("Error loading watchlist from %s: %s", file_path, e)

        _LOG.info("Loaded %d watchlists", len(self._watchlists))

    def get_default_universe(self) -> list[str]:
        """
        Get default universe of stocks to monitor.

        Returns:
            List of ticker symbols
        """
        # S&P 500 top liquid names + major tech
        return [
            # Major indices ETFs
            "SPY",
            "QQQ",
            "IWM",
            "DIA",
            # Mega cap tech
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "META",
            "TSLA",
            "NVDA",
            # Other major names
            "JPM",
            "BAC",
            "XOM",
            "CVX",
            "JNJ",
            "V",
            "MA",
            "WMT",
            "PG",
            "HD",
            "DIS",
            "NFLX",
            "PYPL",
            "ADBE",
            "CRM",
            "INTC",
            "AMD",
            "QCOM",
            # High beta / momentum
            "COIN",
            "RIOT",
            "MARA",
            "PLTR",
            "SOFI",
        ]
