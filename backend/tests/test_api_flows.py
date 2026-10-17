"""In-process API tests using isolated temporary SQLite databases."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.database import get_db
from backend.market_data import Instrument, MarketType
from backend.main import allowed_origins, app
from backend.rate_limit import _hits, _lock


@pytest.fixture
def api_client(db):
    with _lock:
        _hits.clear()
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)

    def override_database():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_database
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def register(client: TestClient, email: str) -> tuple[str, list[str]]:
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/api/v1/auth/register",
        headers={"X-CSRF-Token": csrf},
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201
    return response.json()["csrf_token"], response.headers.get_list("set-cookie")


def test_http_registration_auth_cookie_and_logout(api_client):
    csrf, set_cookies = register(api_client, "http-user@example.com")
    session_cookie = api_client.cookies.get("gs_session")
    assert session_cookie
    assert any(
        "gs_session=" in cookie and "httponly" in cookie.lower() and "samesite=lax" in cookie.lower()
        for cookie in set_cookies
    )
    assert api_client.get("/api/v1/auth/me").json()["user"]["email"] == "http-user@example.com"

    cookies = api_client.get("/api/v1/auth/me").request.headers.get("cookie", "")
    assert "gs_session=" in cookies
    response = api_client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}, json={})
    assert response.status_code == 200
    assert api_client.get("/api/v1/auth/me").status_code == 401


def test_http_trade_csrf_idempotency_and_user_isolation(api_client):
    csrf, _set_cookies = register(api_client, "trader-one@example.com")
    portfolio_url = "/api/v1/portfolio"
    assert api_client.get(portfolio_url).status_code == 200

    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "http-order-1"}
    order = {"symbol": "NIFTYBEES", "side": "buy", "quantity": 1}
    missing_csrf = api_client.post("/api/v1/trades", json=order, headers={"Idempotency-Key": "no-csrf"})
    assert missing_csrf.status_code == 403

    first = api_client.post("/api/v1/trades", json=order, headers=headers)
    repeated = api_client.post("/api/v1/trades", json=order, headers=headers)
    assert first.status_code == repeated.status_code == 200
    assert first.json()["id"] == repeated.json()["id"]
    assert first.json()["mode"] == "simulation"
    assert first.json()["fees"] > 0 and first.json()["slippage"] > 0
    assert api_client.get(portfolio_url).json()["cash"] < 100_000

    conflict = api_client.post(
        "/api/v1/trades",
        json={**order, "quantity": 2},
        headers=headers,
    )
    assert conflict.status_code == 409

    with TestClient(app) as second_client:
        second_csrf, _set_cookies = register(second_client, "trader-two@example.com")
        assert second_client.get(portfolio_url).json()["cash"] == 100_000
        second_order = second_client.post(
            "/api/v1/trades",
            json=order,
            headers={"X-CSRF-Token": second_csrf, "Idempotency-Key": "http-order-1"},
        )
        assert second_order.status_code == 200
        assert second_client.get(portfolio_url).json()["holdings"][0]["quantity"] == 1
    assert api_client.get(portfolio_url).json()["holdings"][0]["quantity"] == 1


def test_http_cors_preflight_allows_credentialed_account_deletion(api_client):
    origin = allowed_origins[0]
    response = api_client.options(
        "/api/v1/auth/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "DELETE" in response.headers["access-control-allow-methods"]


def test_http_strategy_versions_are_user_scoped_and_preview_is_read_only(api_client, monkeypatch):
    csrf, _ = register(api_client, "strategy-one@example.com")
    assert api_client.get("/api/v1/strategy/config").json()["version"] == 0
    config = {
        "min_confidence": 0.7,
        "max_event_age_hours": 12,
        "max_position_percent": 3,
        "max_portfolio_exposure_percent": 40,
        "cooldown_minutes": 30,
    }
    rejected = api_client.put("/api/v1/strategy/config", json=config)
    assert rejected.status_code == 403
    saved = api_client.put("/api/v1/strategy/config", json=config, headers={"X-CSRF-Token": csrf})
    assert saved.status_code == 200 and saved.json()["version"] == 1
    assert len(api_client.get("/api/v1/strategy/versions").json()) == 1

    from backend import main

    monkeypatch.setattr(main, "get_live_news", lambda **_kwargs: [{
        "title": "Nifty rallies on strong growth",
        "description": "",
        "category": "markets",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "url": "https://news.example/article/1",
    }])
    before = api_client.get("/api/v1/portfolio").json()
    preview = api_client.post("/api/v1/strategy/preview", headers={"X-CSRF-Token": csrf}, json={})
    assert preview.status_code == 200
    assert preview.json()["orders_generated"] is False
    assert preview.json()["results"][0]["action"] == "BUY"
    assert api_client.get("/api/v1/portfolio").json() == before

    with TestClient(app) as second_client:
        second_csrf, _ = register(second_client, "strategy-two@example.com")
        assert second_client.get("/api/v1/strategy/config").json()["version"] == 0
        second_saved = second_client.put(
            "/api/v1/strategy/config",
            json={**config, "min_confidence": 0.8},
            headers={"X-CSRF-Token": second_csrf},
        )
        assert second_saved.json()["version"] == 1

    one_user_versions = api_client.get("/api/v1/strategy/versions").json()
    assert one_user_versions[0]["config"]["min_confidence"] == 0.7


def test_http_strategy_config_rejects_out_of_range_risk_values(api_client):
    csrf, _ = register(api_client, "strategy-validation@example.com")
    response = api_client.put(
        "/api/v1/strategy/config",
        headers={"X-CSRF-Token": csrf},
        json={
            "min_confidence": 0.7,
            "max_event_age_hours": 12,
            "max_position_percent": 3,
            "max_portfolio_exposure_percent": 95,
            "cooldown_minutes": 30,
        },
    )
    assert response.status_code == 422


def test_http_global_simulator_kill_switch_blocks_manual_orders(api_client, monkeypatch):
    csrf, _ = register(api_client, "kill-switch@example.com")
    monkeypatch.setenv("SIMULATOR_KILL_SWITCH", "true")
    response = api_client.post(
        "/api/v1/trades",
        json={"symbol": "NIFTYBEES", "side": "buy", "quantity": 1},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "kill-switch-order"},
    )
    assert response.status_code == 503
    assert "kill switch" in response.json()["detail"]
    assert api_client.get("/api/v1/portfolio").json()["holdings"] == []


def test_market_endpoints_require_auth_and_watchlist_is_account_scoped(api_client, monkeypatch):
    from backend import main

    assert api_client.get("/api/v1/markets/status").status_code == 401
    first_csrf, _ = register(api_client, "watchlist-one@example.com")

    class SearchFixture:
        def search_instruments(self, query, limit=20):
            assert query == "RELIANCE"
            return [Instrument(
                market_type=MarketType.EQUITY,
                symbol="NSE:RELIANCE",
                provider="fixture",
                name="Reliance Industries",
                exchange="NSE",
                quote_currency="INR",
                instrument_key="fixture-key",
            )]

    monkeypatch.setattr(main, "get_market_data_provider", lambda *_args, **_kwargs: SearchFixture())
    search = api_client.get("/api/v1/markets/instruments?market_type=EQUITY&q=RELIANCE")
    assert search.status_code == 200 and search.json()[0]["symbol"] == "NSE:RELIANCE"
    saved = api_client.post(
        "/api/v1/watchlist",
        headers={"X-CSRF-Token": first_csrf},
        json={"market_type": "EQUITY", "symbol": "NSE:RELIANCE"},
    )
    assert saved.status_code == 201
    assert api_client.get("/api/v1/watchlist").json()[0]["symbol"] == "NSE:RELIANCE"

    with TestClient(app) as second_client:
        second_csrf, _ = register(second_client, "watchlist-two@example.com")
        assert second_client.get("/api/v1/watchlist").json() == []
        cross_account_delete = second_client.delete(
            "/api/v1/watchlist?market_type=EQUITY&symbol=NSE%3ARELIANCE",
            headers={"X-CSRF-Token": second_csrf},
        )
        assert cross_account_delete.status_code == 404
    assert api_client.get("/api/v1/watchlist").json()[0]["symbol"] == "NSE:RELIANCE"


def test_http_production_disables_demo_quotes_trades_and_synthetic_backtests(api_client, monkeypatch):
    csrf, _ = register(api_client, "production-guard@example.com")
    monkeypatch.setenv("APP_ENV", "production")
    market = api_client.get("/api/v1/market")
    backtest = api_client.get("/api/v1/backtest")
    order = api_client.post(
        "/api/v1/trades",
        json={"symbol": "NIFTYBEES", "side": "buy", "quantity": 1},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "production-guard-order"},
    )
    assert market.status_code == backtest.status_code == order.status_code == 503
    assert api_client.get("/api/v1/portfolio").json()["holdings"] == []


def test_historical_replay_is_authenticated_csrf_protected_and_does_not_touch_portfolio(api_client):
    csrf, _ = register(api_client, "backtest-user@example.com")
    strategy = api_client.put(
        "/api/v1/strategy/config",
        headers={"X-CSRF-Token": csrf},
        json={
            "enabled": False,
            "min_confidence": 0.65,
            "max_event_age_hours": 24,
            "max_position_percent": 5,
            "max_portfolio_exposure_percent": 50,
            "cooldown_minutes": 0,
            "daily_loss_limit_percent": 5,
        },
    )
    assert strategy.status_code == 200
    bars = [
        {
            "market_type": "EQUITY", "symbol": "NIFTYBEES", "timestamp": "2025-01-06T09:15:00+05:30",
            "open": 100, "high": 105, "low": 98, "close": 102, "quote_currency": "INR",
        },
        {
            "market_type": "EQUITY", "symbol": "NIFTYBEES", "timestamp": "2025-01-07T09:15:00+05:30",
            "open": 110, "high": 125, "low": 108, "close": 120, "quote_currency": "INR",
        },
    ]
    payload = {
        "dataset_name": "API fixture",
        "data_rights_confirmed": True,
        "strategy_version": 1,
        "starting_cash": 100_000,
        "candles": bars,
        "news": [{
            "title": "Nifty rallies on strong growth",
            "published_at": "2025-01-06T09:15:00+05:30",
            "url": "https://fixture.example/api-backtest",
        }],
    }
    before = api_client.get("/api/v1/portfolio").json()
    no_csrf = api_client.post("/api/v1/backtest/replay", json=payload)
    assert no_csrf.status_code == 403

    response = api_client.post(
        "/api/v1/backtest/replay",
        headers={"X-CSRF-Token": csrf},
        json=payload,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["filled_trade_count"] == 1
    assert result["strategy_version"] == 1
    assert result["trades"][0]["timestamp"] == "2025-01-07T03:45:00+00:00"
    assert result["data_rights_attested"] is True
    assert api_client.get("/api/v1/portfolio").json() == before

    invalid = api_client.post(
        "/api/v1/backtest/replay",
        headers={"X-CSRF-Token": csrf},
        json={**payload, "data_rights_confirmed": False},
    )
    assert invalid.status_code == 422

    missing_strategy = api_client.post(
        "/api/v1/backtest/replay",
        headers={"X-CSRF-Token": csrf},
        json={**payload, "strategy_version": 9},
    )
    assert missing_strategy.status_code == 404

    with TestClient(app) as second_client:
        second_csrf, _ = register(second_client, "backtest-other-user@example.com")
        foreign_version = second_client.post(
            "/api/v1/backtest/replay",
            headers={"X-CSRF-Token": second_csrf},
            json={**payload, "strategy_version": 1},
        )
        assert foreign_version.status_code == 404


def test_historical_replay_rejects_oversized_upload_and_requires_auth(api_client):
    unauthenticated = api_client.post("/api/v1/backtest/replay", content=b"{}")
    assert unauthenticated.status_code == 401

    csrf, _ = register(api_client, "backtest-size@example.com")
    oversized = api_client.post(
        "/api/v1/backtest/replay",
        headers={"X-CSRF-Token": csrf},
        content=b" " * 5_000_001,
    )
    assert oversized.status_code == 413
