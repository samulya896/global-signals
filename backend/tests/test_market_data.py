"""Provider adapters are verified against fixtures and never make live requests."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.market_data import (
    DataStatus,
    MarketDataError,
    MarketType,
    NormalizedCandle,
    NormalizedQuote,
    TwelveDataForexProvider,
    UpstoxProvider,
    _refresh_quote_status,
    market_data_status,
)


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("unexpected fake HTTP error")


class FakeSession:
    def __init__(self, dispatch):
        self.dispatch = dispatch
        self.calls = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return FakeResponse(self.dispatch(url, params))


def test_upstox_quote_normalizes_unique_bare_symbol_with_read_only_token():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    instrument_key = "NSE_EQ|INE002A01018"

    def dispatch(url, params):
        if url.endswith("/v2/instruments/search"):
            return {"data": [{
                "exchange": "NSE", "segment": "NSE_EQ", "instrument_type": "EQ",
                "trading_symbol": "RELIANCE", "instrument_key": instrument_key,
                "currency": "INR", "tick_size": 0.05, "name": "Reliance Industries",
            }]}
        if url.endswith("/v3/market-quote/quotes"):
            return {"data": {instrument_key: {
                "last_price": 1500.25, "last_trade_time": now.isoformat(), "prev_close_price": 1490,
                "depth": {"buy": [{"price": 1500.2}], "sell": [{"price": 1500.3}]},
            }}}
        if url.endswith("/v2/market/status/NSE"):
            return {"data": {"status": "NORMAL_OPEN"}}
        raise AssertionError(f"Unexpected mocked URL: {url}")

    session = FakeSession(dispatch)
    provider = UpstoxProvider("fixture-token-never-logged", session=session)
    result = provider.get_quote("RELIANCE")

    assert result.market_type is MarketType.EQUITY
    assert result.symbol == "NSE:RELIANCE"
    assert result.price == 1500.25 and result.bid == 1500.2 and result.ask == 1500.3
    assert result.currency == "INR" and result.status is DataStatus.LIVE
    assert result.market_status == "NORMAL_OPEN"
    assert len(session.calls) == 3
    assert all("fixture-token-never-logged" not in call["url"] for call in session.calls)
    assert all(call["headers"]["Authorization"] == "Bearer fixture-token-never-logged" for call in session.calls)


def test_upstox_bare_symbol_is_rejected_when_multiple_exchange_matches_exist():
    class DuplicateProvider(UpstoxProvider):
        def search_instruments(self, query, limit=20):
            from backend.market_data import Instrument

            return [
                Instrument(market_type=MarketType.EQUITY, symbol=f"{exchange}:ABC", provider="fixture",
                           name="ABC", exchange=exchange, quote_currency="INR")
                for exchange in ("NSE", "BSE")
            ]

    with pytest.raises(MarketDataError, match="multiple exchanges"):
        DuplicateProvider("fixture", session=FakeSession(lambda _url, _params: {}))._resolve("ABC")


def test_twelvedata_quote_uses_authorization_header_and_labels_midpoint():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    values = [
        {"datetime": (now - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"), "close": "1.08000"},
        {"datetime": now.strftime("%Y-%m-%d %H:%M:%S"), "close": "1.08125"},
    ]

    def dispatch(url, params):
        if url.endswith("/forex_pairs"):
            return {"data": [{"symbol": "EUR/USD", "currency_group": "Major"}]}
        if url.endswith("/time_series"):
            return {"status": "ok", "values": values}
        raise AssertionError(f"Unexpected mocked URL: {url}")

    session = FakeSession(dispatch)
    provider = TwelveDataForexProvider("fixture-key-never-logged", session=session)
    result = provider.get_quote("EUR/USD")

    assert result.market_type is MarketType.FOREX
    assert result.symbol == "EUR/USD" and result.price == 1.08125
    assert result.base_currency == "EUR" and result.quote_currency == "USD"
    assert result.bid is result.ask is None
    assert result.price_basis.startswith("midpoint")
    assert result.status is DataStatus.LIVE
    assert all("fixture-key-never-logged" not in call["url"] for call in session.calls)
    assert all(call["headers"]["Authorization"] == "apikey fixture-key-never-logged" for call in session.calls)


def test_market_models_reject_invalid_ohlc_and_inverted_spread():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError, match="high/low"):
        NormalizedCandle(
            market_type=MarketType.FOREX, provider="fixture", symbol="EUR/USD", interval="1day",
            timestamp=now, open=1.1, high=1.05, low=1.0, close=1.02, currency="USD",
        )
    with pytest.raises(ValidationError, match="bid cannot exceed ask"):
        NormalizedQuote(
            market_type=MarketType.EQUITY, provider="fixture", source="fixture", symbol="NSE:ABC",
            price=10, currency="INR", quote_currency="INR", bid=10.1, ask=10,
            price_basis="last trade", source_timestamp=now, retrieved_at=now, status=DataStatus.LIVE,
        )


def test_cached_quote_status_is_recomputed_from_source_timestamp():
    now = datetime.now(timezone.utc)
    old_quote = NormalizedQuote(
        market_type=MarketType.FOREX,
        provider="fixture",
        source="fixture",
        symbol="EUR/USD",
        price=1.08,
        currency="USD",
        base_currency="EUR",
        quote_currency="USD",
        price_basis="midpoint",
        source_timestamp=now - timedelta(minutes=20),
        retrieved_at=now,
        status=DataStatus.LIVE,
    )
    assert _refresh_quote_status(old_quote).status is DataStatus.UNAVAILABLE


def test_provider_status_never_returns_credential_values(monkeypatch):
    monkeypatch.setenv("UPSTOX_ANALYTICS_TOKEN", "sensitive-equity-fixture")
    monkeypatch.setenv("UPSTOX_DATA_DISPLAY_AUTHORIZED", "false")
    monkeypatch.setenv("TWELVEDATA_API_KEY", "sensitive-fx-fixture")
    monkeypatch.setenv("TWELVEDATA_DISPLAY_LICENSE_AUTHORIZED", "false")

    status = market_data_status()
    rendered = str(status)
    assert "sensitive-equity-fixture" not in rendered
    assert "sensitive-fx-fixture" not in rendered
    assert status["EQUITY"]["configured"] is False
    assert status["FOREX"]["configured"] is False


def test_provider_http_failures_are_safe_and_count_each_retry_against_limit():
    class UnauthorizedSession:
        def __init__(self):
            self.calls = 0

        def get(self, *_args, **_kwargs):
            self.calls += 1
            return FakeResponse({}, status_code=401)

    unauthorized = UnauthorizedSession()
    provider = TwelveDataForexProvider("secret-fixture", session=unauthorized)
    with pytest.raises(MarketDataError) as rejected:
        provider._request("https://provider.example/test")
    assert rejected.value.status_code == 502
    assert "secret-fixture" not in rejected.value.message
    assert unauthorized.calls == 1

    class RetrySession:
        def __init__(self):
            self.calls = 0

        def get(self, *_args, **_kwargs):
            self.calls += 1
            return FakeResponse({}, status_code=503)

    transient = RetrySession()
    rate_limited = TwelveDataForexProvider("fixture", session=transient, credits_per_minute=1)
    with pytest.raises(MarketDataError) as limited:
        rate_limited._request("https://provider.example/test")
    assert limited.value.status_code == 429
    assert transient.calls == 1
