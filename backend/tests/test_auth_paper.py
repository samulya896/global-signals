from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.auth_api import delete_account, login, password_reset_unavailable, register
from backend.market_data import get_market_data_provider
from backend.market_data import DataStatus, MarketType, NormalizedQuote
from backend.models import AuditEvent, PortfolioSnapshot, SimulatedOrder, StrategyExecution, StrategyVersion, User
from backend.paper import execute_simulated_order, performance, portfolio_snapshot, reset_portfolio
from backend.schemas import Credentials, PasswordConfirmation
from backend.security import create_session, get_session, hash_password, require_csrf, set_session_cookies, verify_password
from backend.tests.conftest import fake_request, fake_response, make_user


def test_private_portfolio_state_is_user_scoped(db):
    first_user = make_user(db, "first@example.com")
    second_user = make_user(db, "second@example.com")
    assert portfolio_snapshot(db, first_user)["cash"] == 100000.0
    assert portfolio_snapshot(db, second_user)["holdings"] == []
    execute_simulated_order(db, first_user, "NIFTYBEES", "buy", 2, "account-a-1")
    assert portfolio_snapshot(db, second_user)["holdings"] == []
    assert portfolio_snapshot(db, first_user)["holdings"][0]["quantity"] == 2


def test_password_is_argon_hashed_and_session_is_revocable(db):
    password_hash = hash_password("correct-horse-battery-staple")
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "correct-horse-battery-staple")
    assert not verify_password(password_hash, "wrong-password")
    user = make_user(db)
    raw_session, _raw_csrf, record = create_session(db, user)
    db.commit()
    request = fake_request(cookies={"gs_session": raw_session})
    found, found_user = get_session(db, request)
    assert found.id == record.id and found_user.id == user.id
    record.revoked_at = record.created_at
    db.commit()
    with pytest.raises(HTTPException) as raised:
        get_session(db, request)
    assert raised.value.status_code == 401


def test_session_cookies_can_be_issued_with_production_security_flags(monkeypatch):
    import backend.security as security
    from starlette.responses import Response

    monkeypatch.setattr(security, "COOKIE_SECURE", True)
    response = Response()
    set_session_cookies(response, "fixture-session", "fixture-csrf")
    cookies = response.headers.getlist("set-cookie")
    assert any("gs_session=" in cookie and "secure" in cookie.lower() and "httponly" in cookie.lower() for cookie in cookies)
    assert any("gs_csrf=" in cookie and "secure" in cookie.lower() and "samesite=lax" in cookie.lower() for cookie in cookies)


def test_login_uses_same_error_for_unknown_email_and_bad_password(db):
    make_user(db, "login@example.com")
    bad_password = Credentials(email="login@example.com", password="wrong-password-123")
    request = fake_request(headers={"x-csrf-token":"csrf"}, cookies={"gs_csrf":"csrf"})
    with pytest.raises(HTTPException) as wrong:
        login(bad_password, request, fake_response(), db)
    missing_user = Credentials(email="missing@example.com", password="wrong-password-123")
    with pytest.raises(HTTPException) as missing:
        login(missing_user, fake_request(headers={"x-csrf-token":"csrf"}, cookies={"gs_csrf":"csrf"}), fake_response(), db)
    assert wrong.value.status_code == missing.value.status_code == 401
    assert wrong.value.detail == missing.value.detail == "Email or password is incorrect."


def test_registration_validates_csrf_and_creates_virtual_account(db):
    request = fake_request(headers={"x-csrf-token":"token-a"}, cookies={"gs_csrf":"token-a"})
    result = register(Credentials(email="new@example.com", password="correct-horse-battery-staple"), request, fake_response(), db)
    assert result["user"]["email"] == "new@example.com"
    assert "password_hash" not in result["user"]
    user = db.query(User).filter_by(email="new@example.com").one()
    assert portfolio_snapshot(db, user)["starting_cash"] == 100000.0
    with pytest.raises(HTTPException) as raised:
        require_csrf(fake_request(headers={"x-csrf-token":"wrong"}, cookies={"gs_csrf":"token-a"}))
    assert raised.value.status_code == 403


def test_simulated_order_is_idempotent_and_accounts_for_fees_and_slippage(db):
    user = make_user(db)
    first = execute_simulated_order(db, user, "NIFTYBEES", "buy", 2, "stable-order-key")
    repeated = execute_simulated_order(db, user, "NIFTYBEES", "buy", 2, "stable-order-key")
    assert first["id"] == repeated["id"]
    assert first["mode"] == "simulation" and first["fees"] > 0 and first["slippage"] > 0
    assert datetime.fromisoformat(first["source_timestamp"]).tzinfo is not None
    assert len(db.query(SimulatedOrder).all()) == 1
    state = portfolio_snapshot(db, user)
    assert state["cash"] < 100000.0 and state["holdings"][0]["quantity"] == 2
    assert round(state["cash"] + first["value"] + first["fees"], 2) == 100000.0
    assert round(first["slippage"], 2) == round(abs(first["price"] - first["quote_price"]) * 2, 2)
    assert performance(db, user)["trade_count"] == 1


def test_idempotency_collision_unknown_instrument_and_short_sale_fail(db):
    user = make_user(db)
    execute_simulated_order(db, user, "NIFTYBEES", "buy", 1, "reuse-key")
    with pytest.raises(HTTPException) as collision:
        execute_simulated_order(db, user, "NIFTYBEES", "buy", 2, "reuse-key")
    assert collision.value.status_code == 409
    with pytest.raises(HTTPException) as unknown:
        execute_simulated_order(db, user, "OTHER", "buy", 1, "unknown-key")
    assert unknown.value.status_code == 400
    with pytest.raises(HTTPException) as short_sale:
        execute_simulated_order(db, user, "BANKBEES", "sell", 1, "short-key")
    assert short_sale.value.status_code == 400


def test_virtual_cash_average_entry_and_realized_unrealized_pnl(db):
    user = make_user(db, starting_cash=Decimal("2000.00"))
    first = execute_simulated_order(db, user, "NIFTYBEES", "buy", 2, "buy-1")
    execute_simulated_order(db, user, "NIFTYBEES", "buy", 2, "buy-2")
    holding = portfolio_snapshot(db, user)["holdings"][0]
    assert holding["quantity"] == 4 and holding["average_cost"] > first["price"]
    sold = execute_simulated_order(db, user, "NIFTYBEES", "sell", 1, "sell-1")
    assert sold["realized_pnl"] < 0
    state = portfolio_snapshot(db, user)
    assert state["holdings"][0]["quantity"] == 3
    assert state["currency"] == "INR" and performance(db, user)["trade_count"] == 3


def test_limits_prevent_overspending_and_order_value_abuse(db):
    user = make_user(db, starting_cash=1000)
    with pytest.raises(HTTPException) as overspend:
        execute_simulated_order(db, user, "NIFTYBEES", "buy", 10, "too-much")
    assert overspend.value.status_code == 400
    with pytest.raises(HTTPException) as max_order:
        execute_simulated_order(db, user, "NIFTYBEES", "buy", 100, "over-limit")
    assert max_order.value.status_code == 400


def test_portfolio_exposure_cap_rejects_without_partial_accounting(db, monkeypatch):
    import backend.paper as paper

    user = make_user(db, starting_cash=1000)
    monkeypatch.setattr(paper, "MAX_EXPOSURE", Decimal("0.10"))
    before = portfolio_snapshot(db, user)
    with pytest.raises(HTTPException) as exposure:
        execute_simulated_order(db, user, "NIFTYBEES", "buy", 1, "exposure-cap")
    assert exposure.value.status_code == 400
    assert "exposure" in exposure.value.detail
    after = portfolio_snapshot(db, user)
    assert after["cash"] == before["cash"]
    assert after["holdings"] == []
    assert db.query(SimulatedOrder).count() == 0


def test_explicit_portfolio_reset_restores_cash_and_preserves_audit(db):
    user = make_user(db)
    execute_simulated_order(db, user, "NIFTYBEES", "buy", 2, "before-reset")
    reset = reset_portfolio(db, user)
    assert reset["cash"] == 100000.0 and reset["holdings"] == []
    assert db.query(SimulatedOrder).filter_by(portfolio_id=user.portfolio.id).count() == 0
    assert db.query(PortfolioSnapshot).filter_by(portfolio_id=user.portfolio.id).count() == 1
    assert db.query(AuditEvent).filter_by(event_type="virtual_portfolio_reset").count() == 1


def test_account_deletion_requires_password_and_cascades_personal_data(db):
    user = make_user(db, "delete-me@example.com")
    db.add(StrategyVersion(user_id=user.id, version=1, config={"enabled": False}))
    db.add(StrategyExecution(
        user_id=user.id,
        article_id="a" * 64,
        strategy_version=1,
        status="rejected",
        reason="test record",
    ))
    db.commit()
    raw_session, raw_csrf, _record = create_session(db, user)
    db.commit()
    request = fake_request(
        cookies={"gs_session":raw_session,"gs_csrf":raw_csrf},
        headers={"x-csrf-token":raw_csrf},
    )
    with pytest.raises(HTTPException) as wrong_password:
        delete_account(PasswordConfirmation(password="not-the-password"), request, fake_response(), db)
    assert wrong_password.value.status_code == 401
    result = delete_account(
        PasswordConfirmation(password="correct-horse-battery-staple"), request, fake_response(), db
    )
    assert result["status"] == "account_deleted"
    assert db.get(User, user.id) is None
    deletion_event = db.query(AuditEvent).filter_by(event_type="account_deleted").one()
    assert deletion_event.user_id is None and deletion_event.object_id is None
    assert db.query(StrategyVersion).filter_by(user_id=user.id).count() == 0
    assert db.query(StrategyExecution).filter_by(user_id=user.id).count() == 0


def test_unavailable_password_reset_is_still_rate_limited(monkeypatch):
    monkeypatch.delenv("EMAIL_PROVIDER_URL", raising=False)
    monkeypatch.delenv("EMAIL_PROVIDER_API_KEY", raising=False)
    request = fake_request()
    for _ in range(5):
        with pytest.raises(HTTPException) as unavailable:
            password_reset_unavailable(request)
        assert unavailable.value.status_code == 503
    with pytest.raises(HTTPException) as limited:
        password_reset_unavailable(request)
    assert limited.value.status_code == 429


def test_synthetic_market_data_is_never_returned_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    provider = get_market_data_provider()
    with pytest.raises(HTTPException) as unavailable:
        provider.get_quote("NIFTYBEES")
    assert unavailable.value.status_code == 503

    monkeypatch.setenv("APP_ENV", "development")
    quote = get_market_data_provider().get_quote("NIFTYBEES")
    assert quote["source"].startswith("synthetic")


def test_concurrent_orders_are_serialized_and_do_not_overdraw(db):
    user = make_user(db)
    user_id = user.id
    bind = db.get_bind()

    def buy(index):
        with Session(bind, autoflush=False, expire_on_commit=False) as session:
            worker_user = session.get(User, user_id)
            return execute_simulated_order(session, worker_user, "NIFTYBEES", "buy", 50, f"parallel-{index}")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(buy, range(4)))
    assert len({result["id"] for result in results}) == 4
    db.expire_all()
    state = portfolio_snapshot(db, db.get(User, user_id))
    assert state["cash"] >= 0 and state["holdings"][0]["quantity"] == 200


def test_forex_order_uses_base_units_and_converts_all_accounting_to_inr(db, monkeypatch):
    from datetime import datetime, timezone
    import backend.paper as paper

    class FixtureFxProvider:
        def get_quote(self, symbol):
            now = datetime.now(timezone.utc)
            if symbol == "EUR/USD":
                base, quote, price = "EUR", "USD", 1.08
            elif symbol == "USD/INR":
                base, quote, price = "USD", "INR", 83.0
            else:
                raise HTTPException(status_code=404, detail="fixture pair missing")
            return NormalizedQuote(
                market_type=MarketType.FOREX,
                provider="fixture-fx",
                source="mocked FX midpoint",
                symbol=symbol,
                price=price,
                currency=quote,
                base_currency=base,
                quote_currency=quote,
                price_basis="fixture midpoint",
                source_timestamp=now,
                retrieved_at=now,
                status=DataStatus.LIVE,
                market_status="weekday fixture",
            )

    provider = FixtureFxProvider()
    monkeypatch.setattr(paper, "get_market_data_provider", lambda *_args, **_kwargs: provider)
    monkeypatch.setenv("SIMULATOR_KILL_SWITCH", "false")
    user = make_user(db)

    order = execute_simulated_order(
        db, user, "EUR/USD", "buy", 100, "fx-buy-1", market_type=MarketType.FOREX
    )
    state = portfolio_snapshot(db, user)

    assert order["market_type"] == "FOREX"
    assert order["base_currency"] == "EUR" and order["quote_currency"] == "USD"
    assert order["quantity_unit"] == "EUR" and order["quantity"] == 100
    assert order["conversion_rate_to_inr"] == 83.0
    assert order["value_inr"] > order["value"]
    assert state["currency"] == "INR" and state["cash"] < 100_000
    assert state["holdings"][0]["quantity_unit"] == "EUR"
    assert state["holdings"][0]["conversion_rate_to_inr"] == 83.0

    sale = execute_simulated_order(
        db, user, "EUR/USD", "sell", 25, "fx-sell-1", market_type=MarketType.FOREX
    )
    remaining = portfolio_snapshot(db, user)
    assert sale["quantity_unit"] == "EUR" and sale["realized_pnl"] < 0
    assert remaining["holdings"][0]["quantity"] == 75


def test_forex_order_fails_without_fresh_conversion_quote(db, monkeypatch):
    from datetime import datetime, timedelta, timezone
    import backend.paper as paper

    class StaleFxProvider:
        def get_quote(self, symbol):
            now = datetime.now(timezone.utc)
            if symbol not in {"EUR/USD", "USD/INR"}:
                raise HTTPException(status_code=404, detail="fixture pair missing")
            stale = symbol == "USD/INR"
            return NormalizedQuote(
                market_type=MarketType.FOREX,
                provider="fixture-fx",
                source="mocked FX midpoint",
                symbol=symbol,
                price=1.08 if symbol == "EUR/USD" else 83.0,
                currency="USD" if symbol == "EUR/USD" else "INR",
                base_currency="EUR" if symbol == "EUR/USD" else "USD",
                quote_currency="USD" if symbol == "EUR/USD" else "INR",
                price_basis="fixture midpoint",
                source_timestamp=now - timedelta(minutes=10) if stale else now,
                retrieved_at=now,
                status=DataStatus.DELAYED if stale else DataStatus.LIVE,
                market_status="weekday fixture",
            )

    monkeypatch.setattr(paper, "get_market_data_provider", lambda *_args, **_kwargs: StaleFxProvider())
    monkeypatch.setenv("SIMULATOR_KILL_SWITCH", "false")
    user = make_user(db)

    with pytest.raises(HTTPException) as raised:
        execute_simulated_order(
            db, user, "EUR/USD", "buy", 100, "fx-stale-1", market_type=MarketType.FOREX
        )
    assert raised.value.status_code == 503
    assert db.query(SimulatedOrder).count() == 0
    assert portfolio_snapshot(db, user)["cash"] == 100_000


def test_forex_conversion_uses_timestamped_inverse_rate_when_direct_pair_is_missing(monkeypatch):
    from datetime import datetime, timezone
    import backend.paper as paper

    now = datetime.now(timezone.utc)

    class InverseFxProvider:
        def get_quote(self, symbol):
            if symbol != "INR/USD":
                raise HTTPException(status_code=404, detail="fixture pair missing")
            return NormalizedQuote(
                market_type=MarketType.FOREX,
                provider="fixture-fx",
                source="mocked inverse FX midpoint",
                symbol=symbol,
                price=0.012,
                currency="USD",
                base_currency="INR",
                quote_currency="USD",
                price_basis="fixture midpoint",
                source_timestamp=now,
                retrieved_at=now,
                status=DataStatus.LIVE,
                market_status="weekday fixture",
            )

    monkeypatch.setattr(paper, "get_market_data_provider", lambda *_args, **_kwargs: InverseFxProvider())
    rate, timestamp = paper._currency_to_inr("USD", now, required_at=now)
    assert rate == Decimal(1) / Decimal("0.012")
    assert timestamp == now
