"""Normalized, read-only market-data adapters for paper trading.

This module never contains an order-routing client. Provider credentials stay in the
backend environment and are sent only in HTTPS authorization headers.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from enum import Enum
import math
import os
import re
import threading
import time
from typing import Any, Protocol
from urllib.parse import quote

import requests
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .simulator import BASE_PRICES, get_quote as get_synthetic_quote


class MarketType(str, Enum):
    EQUITY = "EQUITY"
    FOREX = "FOREX"


class DataStatus(str, Enum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    HISTORICAL = "HISTORICAL"
    UNAVAILABLE = "UNAVAILABLE"


class MarketDataError(HTTPException):
    """Safe provider error. Its detail must never contain credentials or URLs."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(status_code=status_code, detail=message)
        self.message = message


class Instrument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_type: MarketType
    symbol: str
    provider: str
    name: str
    exchange: str | None = None
    base_currency: str | None = None
    quote_currency: str
    instrument_key: str | None = None
    tick_size: float | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_type: MarketType
    provider: str
    source: str
    symbol: str
    price: float = Field(gt=0, allow_inf_nan=False)
    currency: str
    base_currency: str | None = None
    quote_currency: str
    bid: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    ask: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    price_basis: str
    source_timestamp: datetime
    retrieved_at: datetime
    status: DataStatus
    market_status: str | None = None
    change_percent: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        # Keep existing simulator call sites compatible while callers migrate to attributes.
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    @model_validator(mode="after")
    def validate_quote(self):
        if self.source_timestamp.tzinfo is None or self.retrieved_at.tzinfo is None:
            raise ValueError("Quote timestamps must include a timezone.")
        if self.source_timestamp > self.retrieved_at + timedelta(minutes=5):
            raise ValueError("Quote source timestamp is implausibly far in the future.")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("Quote bid cannot exceed ask.")
        if self.base_currency and self.quote_currency == self.base_currency:
            raise ValueError("A currency pair must have different base and quote currencies.")
        return self


class NormalizedCandle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_type: MarketType
    provider: str
    symbol: str
    interval: str
    timestamp: datetime
    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)
    volume: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str
    status: DataStatus = DataStatus.HISTORICAL
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_candle(self):
        if self.timestamp.tzinfo is None:
            raise ValueError("Candle timestamps must include a timezone.")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("Candle high/low values do not contain the open and close.")
        if self.low > self.high:
            raise ValueError("Candle low cannot exceed high.")
        return self


class MarketDataProvider(Protocol):
    name: str
    market_type: MarketType

    def search_instruments(self, query: str, limit: int = 20) -> list[Instrument]: ...

    def get_quote(self, symbol: str) -> NormalizedQuote: ...

    def get_candles(
        self, symbol: str, interval: str, start_date: date, end_date: date, limit: int = 300
    ) -> list[NormalizedCandle]: ...


def _parse_timestamp(value: Any, *, naive_timezone: timezone = timezone.utc) -> datetime:
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        epoch = float(value)
        if epoch > 10_000_000_000:
            epoch /= 1000
        parsed = datetime.fromtimestamp(epoch, tz=timezone.utc)
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=naive_timezone)
    else:
        raise ValueError("Provider timestamp is missing or invalid.")
    if parsed.utcoffset() is None:
        raise ValueError("Provider timestamp has no timezone.")
    if parsed > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError("Provider timestamp is in the future.")
    return parsed.astimezone(timezone.utc)


def _positive_number(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Provider {field_name} is not numeric.") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"Provider {field_name} must be finite and positive.")
    return number


def _data_status(source_timestamp: datetime, market: MarketType, now: datetime) -> DataStatus:
    age = (now - source_timestamp).total_seconds()
    if age < -5:
        raise ValueError("Provider timestamp is in the future.")
    live_window = 120 if market is MarketType.FOREX else 90
    delayed_window = 15 * 60 if market is MarketType.FOREX else 30 * 60
    if age <= live_window:
        return DataStatus.LIVE
    if age <= delayed_window:
        return DataStatus.DELAYED
    return DataStatus.UNAVAILABLE


def _refresh_quote_status(quote: NormalizedQuote) -> NormalizedQuote:
    """Re-evaluate cache hits so an old quote cannot keep a misleading LIVE label."""
    now = datetime.now(timezone.utc)
    status = _data_status(quote.source_timestamp, quote.market_type, now)
    if quote.market_type is MarketType.EQUITY and quote.market_status != "NORMAL_OPEN" and status is DataStatus.LIVE:
        status = DataStatus.DELAYED
    return quote.model_copy(update={"status": status, "retrieved_at": now})


class _CachedHttpProvider:
    """Small process-local response cache, request limiter, and bounded retry loop."""

    auth_scheme = "Bearer"

    def __init__(
        self,
        token: str,
        *,
        per_minute_limit: int,
        session: Any = None,
        per_second_limit: int | None = None,
        per_half_hour_limit: int | None = None,
    ):
        self._token = token
        self._session = session or requests
        self._limit = per_minute_limit
        self._per_second_limit = per_second_limit
        self._per_half_hour_limit = per_half_hour_limit
        self._requests: list[float] = []
        self._cache: dict[tuple[Any, ...], tuple[float, Any]] = {}
        self._lock = threading.RLock()

    def _cached(self, key: tuple[Any, ...], ttl: int, loader):
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and cached[0] > now:
                return cached[1]
        value = loader()
        with self._lock:
            self._cache[key] = (time.monotonic() + ttl, value)
        return value

    def _request(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(3):
            now = time.monotonic()
            with self._lock:
                retention = 1800 if self._per_half_hour_limit is not None else 60
                self._requests = [stamp for stamp in self._requests if now - stamp < retention]
                in_last_minute = sum(now - stamp < 60 for stamp in self._requests)
                in_last_second = sum(now - stamp < 1 for stamp in self._requests)
                if (
                    in_last_minute >= self._limit
                    or (self._per_second_limit is not None and in_last_second >= self._per_second_limit)
                    or (self._per_half_hour_limit is not None and len(self._requests) >= self._per_half_hour_limit)
                ):
                    raise MarketDataError("Provider request limit reached. Wait before refreshing.", 429)
                self._requests.append(now)
            try:
                response = self._session.get(
                    url,
                    params=params or {},
                    headers={"Authorization": f"{self.auth_scheme} {self._token}"},
                    timeout=(3.05, 10),
                )
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        retry_after = response.headers.get("Retry-After", "")
                        try:
                            delay = min(2.0, max(0.1, float(retry_after)))
                        except (TypeError, ValueError):
                            delay = 0.2 * (2**attempt)
                        time.sleep(delay)
                        continue
                    if response.status_code == 429:
                        raise MarketDataError("Market-data provider rate limit reached; try again later.", 429)
                    raise MarketDataError("Market-data provider is temporarily unavailable.", 502)
                if response.status_code >= 400:
                    raise MarketDataError("Market-data provider rejected the request or credentials.", 502)
                try:
                    body = response.json()
                except ValueError as exc:
                    raise MarketDataError("Market-data provider returned malformed JSON.", 502) from exc
            except MarketDataError:
                raise
            except requests.RequestException as exc:
                if attempt < 2:
                    time.sleep(0.2 * (2**attempt))
                    continue
                raise MarketDataError("Market-data provider could not be reached.", 502) from exc
            if not isinstance(body, dict):
                raise MarketDataError("Market-data provider returned an unexpected response.", 502)
            if body.get("status") == "error" or body.get("status") == "failed":
                raise MarketDataError("Market-data provider rejected the request or returned no data.", 502)
            return body
        raise MarketDataError("Market-data provider is temporarily unavailable.", 502)


class UpstoxProvider(_CachedHttpProvider):
    """Read-only Upstox adapter. No order endpoint is implemented or called."""

    name = "Upstox"
    market_type = MarketType.EQUITY
    base_url = "https://api.upstox.com"
    _symbol_pattern = re.compile(r"^(NSE|BSE):([A-Z0-9&._-]{1,24})$")
    _intervals = {
        "1min": ("minutes", 1),
        "5min": ("minutes", 5),
        "15min": ("minutes", 15),
        "30min": ("minutes", 30),
        "1h": ("hours", 1),
        "4h": ("hours", 4),
        "1day": ("days", 1),
    }

    def __init__(self, token: str, *, session: Any = None):
        super().__init__(
            token,
            per_minute_limit=450,
            per_second_limit=50,
            per_half_hour_limit=1800,
            session=session,
        )

    def _api(self, path: str, params: dict[str, Any] | None = None):
        url = f"{self.base_url}{path}"
        return self._request(url, params)

    def search_instruments(self, query: str, limit: int = 20) -> list[Instrument]:
        query = query.strip()[:50]
        if len(query) < 1:
            return []
        limit = max(1, min(limit, 30))
        cache_key = ("search", query.casefold(), limit)

        def load():
            body = self._api(
                "/v2/instruments/search",
                {
                    "query": query,
                    "exchanges": "NSE,BSE",
                    "segments": "EQ",
                    "instrument_types": "EQ",
                    "page_number": 1,
                    "records": limit,
                },
            )
            rows = body.get("data")
            if not isinstance(rows, list):
                raise MarketDataError("Upstox returned an invalid instrument list.", 502)
            result = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                exchange = str(row.get("exchange") or "").upper()
                segment = str(row.get("segment") or "").upper()
                kind = str(row.get("instrument_type") or "").upper()
                trading_symbol = str(row.get("trading_symbol") or "").upper()
                instrument_key = row.get("instrument_key")
                currency = str(row.get("currency") or "INR").upper()
                if (
                    exchange not in {"NSE", "BSE"}
                    or segment not in {"NSE_EQ", "BSE_EQ"}
                    or kind != "EQ"
                    or not trading_symbol
                    or not isinstance(instrument_key, str)
                ):
                    continue
                result.append(
                    Instrument(
                        market_type=MarketType.EQUITY,
                        symbol=f"{exchange}:{trading_symbol}",
                        provider=self.name,
                        name=str(row.get("name") or trading_symbol),
                        exchange=exchange,
                        quote_currency=currency,
                        instrument_key=instrument_key,
                        tick_size=_optional_positive(row.get("tick_size")),
                        metadata={"segment": segment, "isin": row.get("isin")},
                    )
                )
            return result

        return self._cached(cache_key, 3600, load)

    def _resolve(self, symbol: str) -> Instrument:
        normalized = symbol.strip().upper()
        match = self._symbol_pattern.fullmatch(normalized)
        if match:
            exchange, trading_symbol = match.groups()
        elif re.fullmatch(r"[A-Z0-9&._-]{1,24}", normalized):
            exchange, trading_symbol = None, normalized
        else:
            raise MarketDataError("Choose an NSE:SYMBOL or BSE:SYMBOL from instrument search.", 422)
        results = self.search_instruments(trading_symbol, 30)
        matches = [instrument for instrument in results if instrument.symbol.split(":", 1)[-1] == trading_symbol]
        if exchange:
            matches = [instrument for instrument in matches if instrument.exchange == exchange]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise MarketDataError("This symbol is listed on multiple exchanges; choose NSE:SYMBOL or BSE:SYMBOL.", 422)
        raise MarketDataError("The selected equity is not supported by Upstox instrument search.", 422)

    def _exchange_status(self, exchange: str) -> str:
        cache_key = ("market-status", exchange)

        def load():
            body = self._api(f"/v2/market/status/{exchange}")
            data = body.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("status"), str):
                raise MarketDataError("Upstox returned an invalid exchange status.", 502)
            return data["status"].upper()

        return self._cached(cache_key, 5, load)

    def get_quote(self, symbol: str) -> NormalizedQuote:
        instrument = self._resolve(symbol)
        cache_key = ("quote", instrument.instrument_key)

        def load():
            body = self._api("/v3/market-quote/quotes", {"instrument_key": instrument.instrument_key})
            data = body.get("data")
            if not isinstance(data, dict):
                raise MarketDataError("Upstox returned an invalid quote response.", 502)
            item = data.get(instrument.instrument_key)
            if item is None:
                item = next(
                    (value for value in data.values()
                     if isinstance(value, dict) and value.get("instrument_token") == instrument.instrument_key),
                    None,
                )
            if not isinstance(item, dict):
                raise MarketDataError("Upstox did not return a quote for the selected equity.", 502)
            price = _positive_number(item.get("last_price"), "last price")
            source_time = _parse_timestamp(item.get("last_trade_time"))
            now = datetime.now(timezone.utc)
            exchange_status = self._exchange_status(instrument.exchange or "NSE")
            status = _data_status(source_time, MarketType.EQUITY, now)
            if exchange_status != "NORMAL_OPEN" and status is DataStatus.LIVE:
                status = DataStatus.DELAYED
            depth = item.get("depth") if isinstance(item.get("depth"), dict) else {}
            bids = depth.get("buy") if isinstance(depth.get("buy"), list) else []
            asks = depth.get("sell") if isinstance(depth.get("sell"), list) else []
            bid = _optional_positive(bids[0].get("price")) if bids and isinstance(bids[0], dict) else None
            ask = _optional_positive(asks[0].get("price")) if asks and isinstance(asks[0], dict) else None
            prev = _optional_positive(item.get("prev_close_price"))
            change_percent = ((price / prev) - 1) * 100 if prev else None
            return NormalizedQuote(
                market_type=MarketType.EQUITY,
                provider=self.name,
                source="Upstox read-only exchange snapshot",
                symbol=instrument.symbol,
                price=price,
                currency=instrument.quote_currency,
                quote_currency=instrument.quote_currency,
                bid=bid,
                ask=ask,
                price_basis="last trade",
                source_timestamp=source_time,
                retrieved_at=now,
                status=status,
                market_status=exchange_status,
                change_percent=change_percent,
                metadata={
                    "instrument_key": instrument.instrument_key,
                    "tick_size": instrument.tick_size,
                    "exchange": instrument.exchange,
                },
            )

        return _refresh_quote_status(self._cached(cache_key, 2, load))

    def get_candles(
        self, symbol: str, interval: str, start_date: date, end_date: date, limit: int = 300
    ) -> list[NormalizedCandle]:
        if interval not in self._intervals:
            raise MarketDataError("Supported NSE/BSE chart intervals: 1min, 5min, 15min, 30min, 1h, 4h, 1day.", 422)
        if start_date > end_date or end_date > date.today():
            raise MarketDataError("Candle dates must be chronological and cannot end in the future.", 422)
        if limit < 1 or limit > 1000:
            raise MarketDataError("Candle limit must be between 1 and 1000.", 422)
        instrument = self._resolve(symbol)
        unit, step = self._intervals[interval]
        if unit == "minutes" and step <= 15 and end_date - start_date > timedelta(days=30):
            raise MarketDataError("Upstox allows at most one month for 1–15 minute history.", 422)
        if unit == "minutes" and step > 15 and end_date - start_date > timedelta(days=92):
            raise MarketDataError("Upstox allows at most one quarter for this intraday interval.", 422)
        if unit == "hours" and end_date - start_date > timedelta(days=92):
            raise MarketDataError("Upstox allows at most one quarter for hourly history.", 422)
        key = ("candles", instrument.instrument_key, interval, start_date, end_date, limit)

        def load():
            encoded = quote(instrument.instrument_key or "", safe="")
            body = self._api(
                f"/v3/historical-candle/{encoded}/{unit}/{step}/{end_date.isoformat()}/{start_date.isoformat()}"
            )
            return _parse_upstox_candles(body, instrument, interval, limit)

        return self._cached(key, 60, load)


class TwelveDataForexProvider(_CachedHttpProvider):
    """Twelve Data composite FX REST adapter; only mid-price data is represented."""

    name = "Twelve Data Forex composite"
    market_type = MarketType.FOREX
    auth_scheme = "apikey"
    base_url = "https://api.twelvedata.com"
    _pair_pattern = re.compile(r"^([A-Z]{3})/([A-Z]{3})$")
    _intervals = {"1min", "5min", "15min", "30min", "45min", "1h", "2h", "4h", "1day", "1week", "1month"}

    def __init__(self, token: str, *, session: Any = None, credits_per_minute: int = 8):
        super().__init__(token, per_minute_limit=max(1, min(credits_per_minute, 2000)), session=session)

    def _api(self, path: str, params: dict[str, Any] | None = None):
        url = f"{self.base_url}{path}"
        body = self._request(url, params)
        if body.get("status") not in {None, "ok", "success"}:
            raise MarketDataError("Twelve Data rejected the request or returned no data.", 502)
        return body

    def search_instruments(self, query: str, limit: int = 20) -> list[Instrument]:
        query = query.strip().upper().replace("-", "/")
        if not query:
            return []
        limit = max(1, min(limit, 30))
        cache_key = ("forex-pairs", query)

        def load():
            match = self._pair_pattern.fullmatch(query)
            if match:
                rows = self._api("/forex_pairs", {"symbol": query, "outputsize": 30}).get("data")
            elif re.fullmatch(r"[A-Z]{3}", query):
                base = self._api("/forex_pairs", {"currency_base": query, "outputsize": 30}).get("data")
                quote_rows = self._api("/forex_pairs", {"currency_quote": query, "outputsize": 30}).get("data")
                rows = (base if isinstance(base, list) else []) + (quote_rows if isinstance(quote_rows, list) else [])
            else:
                rows = []
            if not isinstance(rows, list):
                raise MarketDataError("Twelve Data returned an invalid forex instrument list.", 502)
            unique: dict[str, Instrument] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol") or "").upper()
                pair = self._pair_pattern.fullmatch(symbol)
                if not pair:
                    continue
                base_currency, quote_currency = pair.groups()
                unique[symbol] = Instrument(
                    market_type=MarketType.FOREX,
                    symbol=symbol,
                    provider=self.name,
                    name=f"{base_currency} / {quote_currency}",
                    exchange="FOREX composite",
                    base_currency=base_currency,
                    quote_currency=quote_currency,
                    metadata={"currency_group": row.get("currency_group")},
                )
            return list(unique.values())[:limit]

        return self._cached(cache_key, 86_400, load)

    def _resolve(self, symbol: str) -> Instrument:
        symbol = symbol.strip().upper().replace("-", "/")
        if not self._pair_pattern.fullmatch(symbol):
            raise MarketDataError("Forex symbols must use BASE/QUOTE currency codes, such as EUR/USD.", 422)
        results = self.search_instruments(symbol, 1)
        if not results or results[0].symbol != symbol:
            raise MarketDataError("The currency pair is not listed in the provider's supported forex pairs.", 422)
        return results[0]

    def get_quote(self, symbol: str) -> NormalizedQuote:
        instrument = self._resolve(symbol)
        key = ("quote", instrument.symbol)

        def load():
            body = self._api(
                "/time_series",
                {"symbol": instrument.symbol, "interval": "1min", "outputsize": 2, "timezone": "UTC"},
            )
            values = body.get("values")
            if not isinstance(values, list) or not values:
                raise MarketDataError("Twelve Data returned no forex price points.", 502)
            parsed = []
            for row in values:
                if not isinstance(row, dict):
                    raise MarketDataError("Twelve Data returned an invalid forex candle.", 502)
                stamp = _parse_timestamp(row.get("datetime"))
                price = _positive_number(row.get("close"), "forex midpoint")
                parsed.append((stamp, price))
            parsed.sort(key=lambda item: item[0])
            source_time, price = parsed[-1]
            now = datetime.now(timezone.utc)
            status = _data_status(source_time, MarketType.FOREX, now)
            previous_price = parsed[-2][1] if len(parsed) > 1 else None
            change = ((price / previous_price) - 1) * 100 if previous_price else None
            return NormalizedQuote(
                market_type=MarketType.FOREX,
                provider=self.name,
                source="Twelve Data aggregated forex candle",
                symbol=instrument.symbol,
                price=price,
                currency=instrument.quote_currency or "",
                base_currency=instrument.base_currency,
                quote_currency=instrument.quote_currency,
                bid=None,
                ask=None,
                price_basis="midpoint (OHLC candle close)",
                source_timestamp=source_time,
                retrieved_at=now,
                status=status,
                market_status="24/7 provider composite; OTC source",
                change_percent=change,
                metadata={"interval": "1min", "spread_available": False},
            )

        return _refresh_quote_status(self._cached(key, 30, load))

    def get_candles(
        self, symbol: str, interval: str, start_date: date, end_date: date, limit: int = 300
    ) -> list[NormalizedCandle]:
        if interval not in self._intervals:
            raise MarketDataError("Unsupported Twelve Data forex candle interval.", 422)
        if start_date > end_date or end_date > date.today():
            raise MarketDataError("Candle dates must be chronological and cannot end in the future.", 422)
        if limit < 1 or limit > 5000:
            raise MarketDataError("Candle limit must be between 1 and 5000.", 422)
        instrument = self._resolve(symbol)
        key = ("candles", instrument.symbol, interval, start_date, end_date, limit)

        def load():
            body = self._api(
                "/time_series",
                {
                    "symbol": instrument.symbol,
                    "interval": interval,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "outputsize": limit,
                    "timezone": "UTC",
                    "order": "ASC",
                },
            )
            values = body.get("values")
            if not isinstance(values, list):
                raise MarketDataError("Twelve Data returned an invalid candle list.", 502)
            return _parse_twelvedata_candles(body, instrument, interval, limit)

        return self._cached(key, 60, load)


class SyntheticDemoProvider:
    """Clearly labeled local-only deterministic equities for the existing tutorial."""

    name = "synthetic-demo"
    market_type = MarketType.EQUITY

    def search_instruments(self, query: str, limit: int = 20) -> list[Instrument]:
        needle = query.strip().upper()
        if not needle:
            return []
        return [
            Instrument(
                market_type=MarketType.EQUITY,
                symbol=symbol,
                provider=self.name,
                name=f"{symbol} (synthetic demo)",
                exchange="SIMULATED",
                quote_currency="INR",
                metadata={"synthetic": True},
            )
            for symbol in BASE_PRICES
            if needle in symbol
        ][: max(1, min(limit, 30))]

    def get_quote(self, symbol: str) -> NormalizedQuote:
        try:
            old_quote = get_synthetic_quote(symbol)
        except ValueError as exc:
            raise MarketDataError("Symbol is not in the local synthetic demo universe.", 400) from exc
        now = datetime.now(timezone.utc)
        return NormalizedQuote(
            market_type=MarketType.EQUITY,
            provider=self.name,
            source=old_quote["source"],
            symbol=old_quote["symbol"],
            price=float(old_quote["price"]),
            currency="INR",
            quote_currency="INR",
            price_basis="synthetic demo value",
            source_timestamp=now,
            retrieved_at=now,
            status=DataStatus.UNAVAILABLE,
            market_status="SIMULATION ONLY",
            change_percent=float(old_quote["change_percent"]),
            metadata={"synthetic": True, "not_market_data": True},
        )

    def get_candles(
        self, symbol: str, interval: str, start_date: date, end_date: date, limit: int = 300
    ) -> list[NormalizedCandle]:
        raise MarketDataError("Historical candles are unavailable for synthetic demo prices.", 503)


class UnavailableMarketDataProvider:
    """Fail closed when credentials or data-display authorization is missing."""

    def __init__(self, market_type: MarketType, message: str):
        self.market_type = market_type
        self.name = "unavailable"
        self.message = message

    def search_instruments(self, query: str, limit: int = 20) -> list[Instrument]:
        raise MarketDataError(self.message, 503)

    def get_quote(self, symbol: str) -> NormalizedQuote:
        raise MarketDataError(self.message, 503)

    def get_candles(
        self, symbol: str, interval: str, start_date: date, end_date: date, limit: int = 300
    ) -> list[NormalizedCandle]:
        raise MarketDataError(self.message, 503)


_provider_instances: dict[tuple[Any, ...], MarketDataProvider] = {}
_provider_instances_lock = threading.Lock()


def get_market_data_provider(
    market_type: MarketType | str = MarketType.EQUITY, *, allow_demo: bool = True
) -> MarketDataProvider:
    market = MarketType(str(market_type).upper()) if not isinstance(market_type, MarketType) else market_type
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if market is MarketType.EQUITY:
        token = os.getenv("UPSTOX_ANALYTICS_TOKEN", "").strip()
        allowed = os.getenv("UPSTOX_DATA_DISPLAY_AUTHORIZED", "false").strip().lower() == "true"
        if token and allowed:
            key = (market, token, allowed)
            with _provider_instances_lock:
                if key not in _provider_instances:
                    _provider_instances[key] = UpstoxProvider(token)
                return _provider_instances[key]
        if token and not allowed:
            return UnavailableMarketDataProvider(
                market, "Upstox data is configured but display authorization is not confirmed."
            )
        if allow_demo and app_env == "development":
            return SyntheticDemoProvider()
        return UnavailableMarketDataProvider(
            market, "Configure an authorized read-only Upstox Analytics Token to load equity data."
        )

    token = os.getenv("TWELVEDATA_API_KEY", "").strip()
    allowed = os.getenv("TWELVEDATA_DISPLAY_LICENSE_AUTHORIZED", "false").strip().lower() == "true"
    if token and allowed:
        try:
            credits = int(os.getenv("TWELVEDATA_API_CREDITS_PER_MINUTE", "8"))
        except ValueError as exc:
            raise MarketDataError("TWELVEDATA_API_CREDITS_PER_MINUTE must be a whole number.", 503) from exc
        key = (market, token, allowed, credits)
        with _provider_instances_lock:
            if key not in _provider_instances:
                _provider_instances[key] = TwelveDataForexProvider(token, credits_per_minute=credits)
            return _provider_instances[key]
    if token and not allowed:
        return UnavailableMarketDataProvider(
            market, "Twelve Data is configured but display-license authorization is not confirmed."
        )
    return UnavailableMarketDataProvider(
        market, "Configure a licensed Twelve Data FX key and confirm permitted display use on the backend."
    )


def market_data_status() -> dict[str, dict[str, Any]]:
    """Return safe readiness information without revealing credential material."""
    equity = get_market_data_provider(MarketType.EQUITY, allow_demo=False)
    forex = get_market_data_provider(MarketType.FOREX, allow_demo=False)
    return {
        MarketType.EQUITY.value: {
            "provider": equity.name,
            "configured": isinstance(equity, UpstoxProvider),
            "message": getattr(equity, "message", "Read-only Upstox data is enabled."),
        },
        MarketType.FOREX.value: {
            "provider": forex.name,
            "configured": isinstance(forex, TwelveDataForexProvider),
            "message": getattr(forex, "message", "Licensed Twelve Data FX display is enabled."),
        },
    }


def _optional_positive(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _parse_upstox_candles(
    body: dict[str, Any], instrument: Instrument, interval: str, limit: int
) -> list[NormalizedCandle]:
    data = body.get("data")
    rows = data.get("candles") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise MarketDataError("Upstox returned an invalid historical candle list.", 502)
    result = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 5:
            raise MarketDataError("Upstox returned a malformed historical candle.", 502)
        try:
            stamp = _parse_timestamp(row[0])
            result.append(
                NormalizedCandle(
                    market_type=MarketType.EQUITY,
                    provider="Upstox",
                    symbol=instrument.symbol,
                    interval=interval,
                    timestamp=stamp,
                    open=_positive_number(row[1], "candle open"),
                    high=_positive_number(row[2], "candle high"),
                    low=_positive_number(row[3], "candle low"),
                    close=_positive_number(row[4], "candle close"),
                    volume=float(row[5]) if len(row) > 5 and row[5] is not None else None,
                    currency=instrument.quote_currency,
                    metadata={"exchange": instrument.exchange, "instrument_key": instrument.instrument_key},
                )
            )
        except (ValueError, TypeError) as exc:
            raise MarketDataError("Upstox returned invalid candle values or timestamps.", 502) from exc
    result.sort(key=lambda candle: candle.timestamp)
    _validate_candle_sequence(result)
    return result[-limit:]


def _parse_twelvedata_candles(
    body: dict[str, Any], instrument: Instrument, interval: str, limit: int
) -> list[NormalizedCandle]:
    values = body.get("values")
    if not isinstance(values, list):
        raise MarketDataError("Twelve Data returned an invalid historical candle list.", 502)
    result = []
    try:
        for row in values:
            if not isinstance(row, dict):
                raise ValueError("Candle must be an object.")
            result.append(
                NormalizedCandle(
                    market_type=MarketType.FOREX,
                    provider="Twelve Data Forex composite",
                    symbol=instrument.symbol,
                    interval=interval,
                    timestamp=_parse_timestamp(row.get("datetime")),
                    open=_positive_number(row.get("open"), "candle open"),
                    high=_positive_number(row.get("high"), "candle high"),
                    low=_positive_number(row.get("low"), "candle low"),
                    close=_positive_number(row.get("close"), "candle close"),
                    volume=None,
                    currency=instrument.quote_currency or "",
                    metadata={
                        "base_currency": instrument.base_currency,
                        "quote_currency": instrument.quote_currency,
                        "price_basis": "composite midpoint candle",
                    },
                )
            )
    except (ValueError, TypeError) as exc:
        raise MarketDataError("Twelve Data returned invalid candle values or timestamps.", 502) from exc
    result.sort(key=lambda candle: candle.timestamp)
    _validate_candle_sequence(result)
    return result[-limit:]


def _validate_candle_sequence(candles: list[NormalizedCandle]) -> None:
    timestamps = [candle.timestamp for candle in candles]
    if len(timestamps) != len(set(timestamps)):
        raise MarketDataError("Provider returned duplicate candle timestamps.", 502)
    if timestamps != sorted(timestamps):
        raise MarketDataError("Provider candle sequence is not chronological.", 502)
