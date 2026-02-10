"""Thin wrapper around schwab-py for authenticated trading calls."""
from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import logging
from schwab import auth
from schwab.client import Client
from schwab.orders import equities

from autotrade.config import SchwabCredentials
from autotrade.utils.time_utils import now_utc

_LOG = logging.getLogger(__name__)


class SchwabClient(AbstractContextManager["SchwabClient"]):
    """Convenience wrapper that exposes the subset of Schwab Trader API calls the bot needs."""

    def __init__(
        self,
        credentials: SchwabCredentials,
        *,
        token_path: str | Path | None = None,
        enforce_enums: bool = False,
    ) -> None:
        self._credentials = credentials
        self._token_path = Path(token_path or credentials.token_path).expanduser()
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._enforce_enums = enforce_enums
        self._client: Client | None = None
        self._account_hash: str | None = self._normalize_identifier(credentials.account_hash) or None

    def __enter__(self) -> "SchwabClient":
        self.login()
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:  # pragma: no cover - no explicit logout endpoint
        pass

    def login(self) -> None:
        """Create an authenticated Schwab client from the stored token file."""
        if self._client:
            return
        if not self._token_path.exists():
            raise FileNotFoundError(
                f"Schwab token file not found at {self._token_path}. "
                "Run the Schwab login flow to generate it first."
            )
        self._client = auth.client_from_token_file(
            str(self._token_path),
            self._credentials.app_key,
            self._credentials.app_secret,
            enforce_enums=self._enforce_enums,
        )
        if self._account_hash:
            return
        try:
            self._account_hash = self._resolve_account_hash()
        except Exception:
            self._client = None
            self._account_hash = None
            raise

    def get_last_trade_price(self, ticker: str) -> float:
        response = self._require_client().get_quote(ticker.upper())
        payload = self._as_json(response, context=f"quote for {ticker.upper()}")
        price = self._extract_price_from_quote(payload, ticker)
        if price is None:
            raise ValueError(f"No quote price returned for {ticker}")
        return price

    def get_historical_quotes(self, ticker: str, *, span: str = "day", interval: str = "5minute") -> list[dict[str, Any]]:
        params = self._resolve_price_history_params(span, interval)
        history_response = self._require_client().get_price_history(
            ticker.upper(),
            **params,
            need_extended_hours_data=False,
        )
        history = self._as_json(history_response, context=f"price history for {ticker.upper()}")
        candles = history.get("candles", []) if isinstance(history, dict) else []
        normalized: list[dict[str, Any]] = []
        for candle in candles:
            if not isinstance(candle, dict):
                continue
            timestamp = candle.get("datetime")
            if timestamp is None:
                continue
            dt = datetime.fromtimestamp(float(timestamp) / 1000.0, tz=timezone.utc)
            normalized.append(
                {
                    "begins_at": dt.isoformat(),
                    "open_price": float(candle.get("open", 0.0)),
                    "high_price": float(candle.get("high", 0.0)),
                    "low_price": float(candle.get("low", 0.0)),
                    "close_price": float(candle.get("close", 0.0)),
                    "volume": int(candle.get("volume", 0)),
                }
            )
        return normalized

    def get_positions(self) -> dict[str, dict[str, Any]]:
        account = self._fetch_account(snapshot_fields=[Client.Account.Fields.POSITIONS])
        securities = account.get("securitiesAccount", {}) if isinstance(account, dict) else {}
        positions = securities.get("positions", []) if isinstance(securities, dict) else []
        holdings: dict[str, dict[str, Any]] = {}
        for position in positions:
            if not isinstance(position, dict):
                continue
            instrument = position.get("instrument")
            if not isinstance(instrument, dict):
                instrument = {}
            symbol = instrument.get("symbol") or instrument.get("assetId") or instrument.get("symbolId")
            if not symbol:
                continue
            symbol = str(symbol).upper()
            long_qty = position.get("longQuantity")
            short_qty = position.get("shortQuantity")
            quantity = self._to_float(long_qty) - self._to_float(short_qty)
            holdings[symbol] = {
                "quantity": quantity,
                "average_buy_price": self._to_float(position.get("averagePrice")),
                "market_value": self._to_float(position.get("marketValue")),
            }
        return holdings

    def submit_market_order(self, ticker: str, quantity: float, *, side: str) -> Any:
        order_quantity = int(quantity)
        if order_quantity <= 0:
            raise ValueError("Order quantity must be positive")
        side_lower = side.lower()
        if side_lower not in {"buy", "sell"}:
            raise ValueError("Order side must be 'buy' or 'sell'")
        if side_lower == "buy":
            order_builder = equities.equity_buy_market(ticker.upper(), order_quantity)
        else:
            order_builder = equities.equity_sell_market(ticker.upper(), order_quantity)
        return self._require_client().place_order(self._account_hash_required(), order_builder)

    def get_portfolio_profile(self) -> dict[str, Any]:
        try:
            account = self._fetch_account()
        except RuntimeError as exc:
            fallback = self._account_overview()
            if fallback is None:
                raise
            account = fallback
        securities = account.get("securitiesAccount", {}) if isinstance(account, dict) else {}
        balances = securities.get("currentBalances", {}) if isinstance(securities, dict) else {}
        return {
            "market_value": self._to_float(balances.get("marketValue")),
            "cash_available_for_trading": self._to_float(balances.get("cashAvailableForTrading")),
            "cash_available_for_withdrawal": self._to_float(balances.get("cashAvailableForWithdrawal")),
        }

    def get_order_status(self, order_id: str) -> dict[str, Any] | None:
        """Get the status of a specific order by order ID.

        Returns a dict with order details including status, or None if not found.
        """
        client = self._require_client()
        try:
            order_response = client.get_order(self._account_hash_required(), order_id)
            order = self._as_json(order_response, context=f"order {order_id}")
            if isinstance(order, dict):
                return {
                    "order_id": order.get("orderId") or order.get("id"),
                    "status": order.get("status"),
                    "filled_quantity": self._to_float(order.get("filledQuantity")),
                    "remaining_quantity": self._to_float(order.get("remainingQuantity")),
                    "order_activity": order.get("orderActivity"),
                }
            return None
        except Exception as exc:
            _LOG.warning("Failed to get order status for %s: %s", order_id, exc)
            return None

    def cancel_open_orders(self) -> None:
        client = self._require_client()
        try:
            orders_response = client.get_orders_for_account(
                self._account_hash_required(),
                status=Client.Order.Status.WORKING,
            )
            orders = self._as_json(orders_response, context="open orders")
        except (httpx.HTTPError, RuntimeError) as exc:
            _LOG.warning("Failed to retrieve open orders for cancellation: %s", exc)
            return
        except ValueError as exc:
            _LOG.error("Invalid response when retrieving open orders: %s", exc)
            return

        if not isinstance(orders, list):
            return

        for order in orders:
            if not isinstance(order, dict):
                continue
            order_id = order.get("orderId") or order.get("id")
            if not order_id:
                continue
            try:
                client.cancel_order(self._account_hash_required(), order_id)
                _LOG.info("Cancelled order %s", order_id)
            except (httpx.HTTPError, RuntimeError) as exc:
                _LOG.warning("Failed to cancel order %s: %s", order_id, exc)
                continue
            except ValueError as exc:
                _LOG.error("Invalid order ID %s: %s", order_id, exc)
                continue

    @staticmethod
    def now() -> datetime:
        """Get current UTC time with timezone awareness.

        Returns:
            Timezone-aware datetime in UTC
        """
        return now_utc()

    def _fetch_account(self, *, snapshot_fields: list[Client.Account.Fields] | None = None) -> dict[str, Any]:
        client = self._require_client()
        fields = snapshot_fields or []
        if fields:
            response = client.get_account(self._account_hash_required(), fields=fields)
        else:
            response = client.get_account(self._account_hash_required())
        return self._as_json(response, context="account details")

    def _require_client(self) -> Client:
        if not self._client:
            raise RuntimeError("Schwab client is not authenticated. Call login() first.")
        return self._client

    def _account_overview(self) -> dict[str, Any] | None:
        """Fallback for account snapshot when detailed lookup fails."""
        try:
            response = self._require_client().get_accounts()
        except Exception as exc:  # pragma: no cover - live API guard
            _LOG.warning("Unable to load Schwab account overview: %s", exc)
            return None
        payload = self._as_json(response, context="accounts overview")
        accounts: list[Any]
        if isinstance(payload, list):
            accounts = payload
        elif isinstance(payload, dict):
            accounts = []
            for key in ("accounts", "securitiesAccounts"):
                value = payload.get(key)
                if isinstance(value, list):
                    accounts.extend(value)
        else:
            accounts = []
        if not accounts:
            return None
        targets = self._account_match_targets()
        for entry in accounts:
            if not isinstance(entry, dict):
                continue
            candidate = entry
            if "securitiesAccount" in entry and isinstance(entry["securitiesAccount"], dict):
                candidate = entry["securitiesAccount"]
            identifiers = [
                candidate.get("accountHash"),
                candidate.get("accountId"),
                candidate.get("accountNumber"),
            ]
            normalized = {value for identifier in identifiers for value in self._normalized_identifier_variants(identifier)}
            if targets and (targets & normalized):
                return entry
        return accounts[0] if isinstance(accounts[0], dict) else None

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _extract_price_from_quote(payload: Any, ticker: str) -> float | None:
        candidates: list[dict[str, Any]] = []

        def collect(item: Any) -> None:
            if isinstance(item, dict):
                candidates.append(item)
                for val in item.values():
                    collect(val)
            elif isinstance(item, list):
                for entry in item:
                    collect(entry)

        collect(payload)
        ticker_upper = ticker.upper()
        for candidate in candidates:
            symbol = candidate.get("symbol") or candidate.get("ticker")
            if symbol and str(symbol).upper() not in {ticker_upper, "QUOTES"}:
                continue
            for key in (
                "mark",
                "lastPrice",
                "closePrice",
                "regularMarketLastPrice",
                "bidPrice",
                "askPrice",
            ):
                value = candidate.get(key)
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _resolve_price_history_params(span: str, interval: str) -> dict[str, Any]:
        span_normalized = (span or "").lower()
        interval_normalized = (interval or "").lower()
        period_type: Client.PriceHistory.PeriodType
        period: Client.PriceHistory.Period
        frequency_type: Client.PriceHistory.FrequencyType
        frequency: Client.PriceHistory.Frequency

        minute_map = {
            "1minute": Client.PriceHistory.Frequency.EVERY_MINUTE,
            "5minute": Client.PriceHistory.Frequency.EVERY_FIVE_MINUTES,
            "10minute": Client.PriceHistory.Frequency.EVERY_TEN_MINUTES,
            "15minute": Client.PriceHistory.Frequency.EVERY_FIFTEEN_MINUTES,
            "30minute": Client.PriceHistory.Frequency.EVERY_THIRTY_MINUTES,
        }
        if interval_normalized in minute_map:
            period_type = Client.PriceHistory.PeriodType.DAY
            period = Client.PriceHistory.Period.ONE_DAY
            frequency_type = Client.PriceHistory.FrequencyType.MINUTE
            frequency = minute_map[interval_normalized]
            return {
                "period_type": period_type,
                "period": period,
                "frequency_type": frequency_type,
                "frequency": frequency,
            }

        frequency_lookup = {
            "day": (Client.PriceHistory.FrequencyType.DAILY, Client.PriceHistory.Frequency.DAILY),
            "week": (Client.PriceHistory.FrequencyType.WEEKLY, Client.PriceHistory.Frequency.WEEKLY),
            "month": (Client.PriceHistory.FrequencyType.MONTHLY, Client.PriceHistory.Frequency.MONTHLY),
        }
        try:
            frequency_type, frequency = frequency_lookup[interval_normalized]
        except KeyError as exc:
            raise ValueError(f"Unsupported Schwab history interval '{interval}'") from exc

        period_lookup = {
            "month": (Client.PriceHistory.PeriodType.MONTH, Client.PriceHistory.Period.ONE_MONTH),
            "2month": (Client.PriceHistory.PeriodType.MONTH, Client.PriceHistory.Period.TWO_MONTHS),
            "3month": (Client.PriceHistory.PeriodType.MONTH, Client.PriceHistory.Period.THREE_MONTHS),
            "6month": (Client.PriceHistory.PeriodType.MONTH, Client.PriceHistory.Period.SIX_MONTHS),
            "year": (Client.PriceHistory.PeriodType.YEAR, Client.PriceHistory.Period.ONE_YEAR),
            "2year": (Client.PriceHistory.PeriodType.YEAR, Client.PriceHistory.Period.TWO_YEARS),
            "3year": (Client.PriceHistory.PeriodType.YEAR, Client.PriceHistory.Period.THREE_YEARS),
            "5year": (Client.PriceHistory.PeriodType.YEAR, Client.PriceHistory.Period.FIVE_YEARS),
            "10year": (Client.PriceHistory.PeriodType.YEAR, Client.PriceHistory.Period.TEN_YEARS),
            "15year": (Client.PriceHistory.PeriodType.YEAR, Client.PriceHistory.Period.FIFTEEN_YEARS),
            "20year": (Client.PriceHistory.PeriodType.YEAR, Client.PriceHistory.Period.TWENTY_YEARS),
            "ytd": (Client.PriceHistory.PeriodType.YEAR_TO_DATE, Client.PriceHistory.Period.YEAR_TO_DATE),
        }
        if span_normalized in period_lookup:
            period_type, period = period_lookup[span_normalized]
        else:
            period_type = Client.PriceHistory.PeriodType.YEAR
            period = Client.PriceHistory.Period.ONE_YEAR

        return {
            "period_type": period_type,
            "period": period,
            "frequency_type": frequency_type,
            "frequency": frequency,
        }

    @staticmethod
    def _as_json(response: Any, *, context: str) -> Any:
        if isinstance(response, httpx.Response):
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover - live API guard
                raise RuntimeError(f"Schwab API request for {context} failed: {exc}") from exc
            try:
                return response.json()
            except ValueError as exc:
                raise ValueError(f"Unable to parse Schwab {context} response as JSON") from exc
        return response

    def _resolve_account_hash(self) -> str:
        client = self._require_client()
        provided = self._normalize_identifier(self._credentials.account_number)
        if not provided:
            raise ValueError("SCHWAB_ACCOUNT_NUMBER is empty; provide an account hash or account number.")
        targets = self._normalized_identifier_variants(provided)
        account_hash = self._resolve_account_hash_from_numbers(client, targets)
        if account_hash:
            return account_hash
        account_hash = self._resolve_account_hash_from_accounts(client, targets)
        if account_hash:
            return account_hash
        if self._looks_like_hash(provided):
            return provided
        raise ValueError(
            "Unable to resolve Schwab account hash from SCHWAB_ACCOUNT_NUMBER. "
            "Set SCHWAB_ACCOUNT_NUMBER to either the account hash returned by the API "
            "or an account identifier shown in the Schwab dashboard."
        )

    def _resolve_account_hash_from_numbers(self, client: Client, targets: set[str]) -> str | None:
        try:
            response = client.get_account_numbers()
        except Exception as exc:  # pragma: no cover - live API guard
            _LOG.debug("Unable to load Schwab account numbers: %s", exc)
            return None
        payload = self._as_json(response, context="account numbers")
        entries: list[dict[str, Any]]
        if isinstance(payload, list):
            entries = [entry for entry in payload if isinstance(entry, dict)]
        elif isinstance(payload, dict):
            entries = [payload]
        else:
            entries = []
        for entry in entries:
            account_identifier = entry.get("accountNumber") or entry.get("accountId")
            normalized = self._normalized_identifier_variants(account_identifier)
            if targets & normalized:
                account_hash = self._normalize_identifier(entry.get("hashValue") or entry.get("accountHash"))
                if account_hash:
                    return account_hash
        if len(entries) == 1:
            entry = entries[0]
            account_hash = self._normalize_identifier(entry.get("hashValue") or entry.get("accountHash"))
            if account_hash:
                return account_hash
        return None

    def _resolve_account_hash_from_accounts(self, client: Client, targets: set[str]) -> str | None:
        try:
            response = client.get_accounts()
        except Exception as exc:  # pragma: no cover - live API guard
            raise RuntimeError("Unable to resolve Schwab account hash from API.") from exc
        accounts_payload = self._as_json(response, context="accounts overview")
        accounts = self._extract_accounts(accounts_payload)
        for entry in accounts:
            candidate = entry
            if isinstance(entry, dict) and "securitiesAccount" in entry and isinstance(entry["securitiesAccount"], dict):
                candidate = entry["securitiesAccount"]
            identifiers = [
                candidate.get("accountHash"),
                candidate.get("accountId"),
                candidate.get("accountNumber"),
            ]
            normalized = {value for identifier in identifiers for value in self._normalized_identifier_variants(identifier)}
            if targets & normalized:
                account_hash = self._normalize_identifier(candidate.get("accountHash"))
                if account_hash:
                    return account_hash
        if len(accounts) == 1:
            candidate = accounts[0]
            if isinstance(candidate, dict) and "securitiesAccount" in candidate and isinstance(candidate["securitiesAccount"], dict):
                candidate = candidate["securitiesAccount"]
            account_hash = self._normalize_identifier(candidate.get("accountHash"))
            if account_hash:
                return account_hash
        return None

    def _account_hash_required(self) -> str:
        if self._account_hash:
            return self._account_hash
        raise RuntimeError("Schwab account hash not resolved. Ensure login() completed successfully.")

    def _account_match_targets(self) -> set[str]:
        targets: set[str] = set()
        provided = self._normalize_identifier(self._credentials.account_number)
        if provided:
            targets.update(self._normalized_identifier_variants(provided))
        if self._account_hash:
            targets.update(self._normalized_identifier_variants(self._account_hash))
        return targets

    @staticmethod
    def _extract_accounts(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [entry for entry in payload if isinstance(entry, dict)]
        if isinstance(payload, dict):
            accounts: list[dict[str, Any]] = []
            for key in ("accounts", "securitiesAccounts"):
                value = payload.get(key)
                if isinstance(value, list):
                    accounts.extend(entry for entry in value if isinstance(entry, dict))
            if accounts:
                return accounts
            return [payload]
        return []

    @staticmethod
    def _normalize_identifier(value: Any) -> str:
        raw = "" if value is None else str(value)
        return raw.strip()

    def _normalized_identifier_variants(self, value: Any) -> set[str]:
        normalized = self._normalize_identifier(value)
        if not normalized:
            return set()
        variants = {
            normalized,
            normalized.replace("-", ""),
            normalized.replace("-", "").replace(" ", ""),
        }
        normalized_variants: set[str] = set()
        for variant in variants:
            if not variant:
                continue
            normalized_variants.add(variant)
            normalized_variants.add(variant.upper())
            normalized_variants.add(variant.lower())
            digits_only = "".join(ch for ch in variant if ch.isdigit())
            if digits_only:
                normalized_variants.add(digits_only)
                if len(digits_only) >= 4:
                    normalized_variants.add(digits_only[-4:])
                if len(digits_only) >= 6:
                    normalized_variants.add(digits_only[-6:])
            masked_clean = variant.replace("*", "")
            if masked_clean and masked_clean != variant:
                normalized_variants.add(masked_clean)
                digits_only_masked = "".join(ch for ch in masked_clean if ch.isdigit())
                if digits_only_masked:
                    normalized_variants.add(digits_only_masked)
                    if len(digits_only_masked) >= 4:
                        normalized_variants.add(digits_only_masked[-4:])
                    if len(digits_only_masked) >= 6:
                        normalized_variants.add(digits_only_masked[-6:])
        return {entry for entry in normalized_variants if entry}

    @staticmethod
    def _looks_like_hash(value: str) -> bool:
        candidate = (value or "").strip()
        if not candidate:
            return False
        candidate_no_dash = candidate.replace("-", "")
        has_alpha = any(ch.isalpha() for ch in candidate_no_dash)
        has_digit = any(ch.isdigit() for ch in candidate_no_dash)
        return has_alpha and has_digit and len(candidate_no_dash) >= 6
