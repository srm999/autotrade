"""Thin wrapper around robin_stocks for authenticated trading calls."""
from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Iterable

try:
    import robin_stocks.robinhood as rh
except ModuleNotFoundError as exc:  # pragma: no cover - library import guard
    raise ImportError(
        "robin_stocks is required. Install with `pip install robin-stocks`"
    ) from exc

from autotrade.config import RobinhoodCredentials


class RobinhoodClient(AbstractContextManager["RobinhoodClient"]):
    def __init__(self, credentials: RobinhoodCredentials, *, expire: bool = True) -> None:
        self._credentials = credentials
        self._logout_on_exit = expire
        self._logged_in = False

    def __enter__(self) -> "RobinhoodClient":
        self.login()
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        if self._logout_on_exit and self._logged_in:
            rh.authentication.logout()
            self._logged_in = False

    def login(self) -> None:
        if self._logged_in:
            return
        kwargs: dict[str, Any] = {}
        if self._credentials.device_token:
            kwargs["device_token"] = self._credentials.device_token
        if self._credentials.mfa_code:
            kwargs["mfa_code"] = self._credentials.mfa_code
        rh.authentication.login(
            username=self._credentials.username,
            password=self._credentials.password,
            **kwargs,
        )
        self._logged_in = True

    def get_last_trade_price(self, ticker: str) -> float:
        quote = rh.stocks.get_latest_price(ticker, includeExtendedHours=False)
        if not quote:
            raise ValueError(f"No quote returned for {ticker}")
        return float(quote[0])

    def get_historical_quotes(self, ticker: str, span: str = "day", interval: str = "5minute") -> list[dict[str, Any]]:
        return rh.stocks.get_stock_historicals(ticker, span=span, bounds="regular", interval=interval)

    def get_positions(self) -> list[dict[str, Any]]:
        return rh.account.build_holdings()

    def submit_market_order(self, ticker: str, quantity: float, *, side: str) -> dict[str, Any]:
        side = side.lower()
        if side not in {"buy", "sell"}:
            raise ValueError("Order side must be 'buy' or 'sell'")
        return rh.orders.order_buy_market(ticker, quantity) if side == "buy" else rh.orders.order_sell_market(ticker, quantity)

    def submit_option_order(
        self,
        chain_symbol: str,
        expiration_date: str,
        strike: float,
        option_type: str,
        quantity: int,
        *,
        side: str,
    ) -> dict[str, Any]:
        side = side.lower()
        option_type = option_type.lower()
        if side not in {"buy", "sell"}:
            raise ValueError("Option order side must be 'buy' or 'sell'")
        if option_type not in {"call", "put"}:
            raise ValueError("Option type must be 'call' or 'put'")
        return rh.options.order_buy_to_open(
            symbol=chain_symbol,
            quantity=quantity,
            expirationDate=expiration_date,
            strike=strike,
            optionType=option_type,
        ) if side == "buy" else rh.options.order_sell_to_close(
            symbol=chain_symbol,
            quantity=quantity,
            expirationDate=expiration_date,
            strike=strike,
            optionType=option_type,
        )

    def get_option_chain(self, symbol: str, expiration_dates: Iterable[str] | None = None) -> list[dict[str, Any]]:
        dates = list(expiration_dates) if expiration_dates else None
        chain = rh.options.find_tradable_options(
            symbol=symbol,
            expirationDate=dates[0] if dates and len(dates) == 1 else None,
        )
        if dates and len(dates) > 1:
            extra: list[dict[str, Any]] = []
            for date in dates[1:]:
                extra.extend(rh.options.find_tradable_options(symbol=symbol, expirationDate=date))
            chain.extend(extra)
        return chain

    def get_account_profile(self) -> dict[str, Any]:
        return rh.profiles.load_account_profile()

    def get_portfolio_profile(self) -> dict[str, Any]:
        return rh.profiles.load_portfolio_profile()

    def cancel_open_orders(self) -> None:
        for order in rh.orders.get_all_open_orders():
            rh.orders.cancel_stock_order(order["id"])

    @staticmethod
    def now() -> datetime:
        return datetime.now()
