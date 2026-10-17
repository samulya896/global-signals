from datetime import datetime, timezone
from decimal import Decimal

from backend.models import SimulatedOrder, StrategyExecution, StrategyVersion
from backend.market_data import DataStatus, MarketType, NormalizedQuote
from backend.tests.conftest import make_user
from backend.worker import is_market_session_open, process_strategy_cycle


def configured_user(db, email="worker@example.com"):
    user = make_user(db, email)
    config = {
        "enabled": True,
        "min_confidence": 0.65,
        "max_event_age_hours": 24,
        "max_position_percent": 10,
        "max_portfolio_exposure_percent": 50,
        "cooldown_minutes": 60,
        "daily_loss_limit_percent": 5,
    }
    db.add(StrategyVersion(user_id=user.id, version=1, config=config))
    db.commit()
    return user


def article(url="https://news.example/nifty-rally"):
    return {
        "title": "Nifty rallies on strong growth",
        "description": "",
        "category": "markets",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
    }


def test_worker_creates_one_simulated_order_and_deduplicates_repeated_article(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("STRATEGY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("SIMULATOR_KILL_SWITCH", "false")
    user = configured_user(db)

    result = process_strategy_cycle(db, [article()], market_open=True)
    repeated = process_strategy_cycle(db, [article()], market_open=True)

    assert result["orders"] == 1
    assert repeated["duplicates"] == 1
    assert db.query(SimulatedOrder).count() == 1
    execution = db.query(StrategyExecution).one()
    assert execution.status == "filled"
    assert execution.simulated_order_id == db.query(SimulatedOrder).one().id
    assert user.portfolio.cash < user.portfolio.starting_cash


def test_worker_honors_global_kill_switch_and_never_executes_in_production(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("STRATEGY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("SIMULATOR_KILL_SWITCH", "true")
    configured_user(db)
    stopped = process_strategy_cycle(db, [article()], market_open=True)
    assert stopped["status"] == "disabled_by_global_switch"
    assert db.query(SimulatedOrder).count() == 0

    monkeypatch.setenv("SIMULATOR_KILL_SWITCH", "false")
    monkeypatch.setenv("APP_ENV", "production")
    production = process_strategy_cycle(db, [article()], market_open=True)
    assert production["status"] == "disabled_outside_development"
    assert db.query(SimulatedOrder).count() == 0


def test_worker_respects_position_cap_and_cooldown(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("STRATEGY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("SIMULATOR_KILL_SWITCH", "false")
    user = configured_user(db)
    record = db.query(StrategyVersion).filter_by(user_id=user.id).one()
    record.config = {**record.config, "max_position_percent": 0.1}
    db.commit()

    too_small = process_strategy_cycle(db, [article()], market_open=True)
    assert too_small["rejected"] == 1
    assert db.query(SimulatedOrder).count() == 0

    # A fresh version and event may execute after raising the position cap.
    record.config = {**record.config, "max_position_percent": 10}
    db.commit()
    filled = process_strategy_cycle(db, [article("https://news.example/second")], market_open=True)
    cooldown = process_strategy_cycle(db, [article("https://news.example/third")], market_open=True)
    assert filled["orders"] == 1
    assert cooldown["rejected"] == 1
    assert db.query(SimulatedOrder).count() == 1


def test_worker_recovers_processing_event_without_duplicate_fill(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("STRATEGY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("SIMULATOR_KILL_SWITCH", "false")
    configured_user(db)
    news = article()
    first = process_strategy_cycle(db, [news], market_open=True)
    execution = db.query(StrategyExecution).one()
    order_id = execution.simulated_order_id
    execution.status = "processing"  # Simulate a worker stopping after the order commit.
    db.commit()

    recovered = process_strategy_cycle(db, [news], market_open=True)

    assert first["orders"] == recovered["orders"] == 1
    assert db.query(SimulatedOrder).count() == 1
    assert execution.status == "filled" and execution.simulated_order_id == order_id


def test_worker_enforces_realized_daily_loss_limit(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("STRATEGY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("SIMULATOR_KILL_SWITCH", "false")
    user = configured_user(db)
    record = db.query(StrategyVersion).filter_by(user_id=user.id).one()
    record.config = {**record.config, "daily_loss_limit_percent": 1}
    db.add(SimulatedOrder(
        portfolio_id=user.portfolio.id,
        idempotency_key="prior-loss",
        request_fingerprint="b" * 64,
        symbol="NIFTYBEES",
        side="sell",
        quantity=1,
        quote_price=Decimal("280.00"),
        fill_price=Decimal("279.86"),
        fees=Decimal("0.28"),
        slippage=Decimal("0.14"),
        realized_pnl=Decimal("-1001.00"),
        status="filled",
        mode="simulation",
        created_at=datetime.now(timezone.utc),
    ))
    db.commit()

    result = process_strategy_cycle(db, [article()], market_open=True)

    assert result["rejected"] == 1
    assert db.query(SimulatedOrder).count() == 1
    assert db.query(StrategyExecution).one().status == "rejected"


def test_worker_market_session_guard_uses_weekday_ist_window():
    assert is_market_session_open(datetime(2026, 10, 19, 4, 0, tzinfo=timezone.utc))
    assert not is_market_session_open(datetime(2026, 10, 17, 4, 0, tzinfo=timezone.utc))
    assert not is_market_session_open(datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc))


def test_worker_can_size_explicit_fx_signal_in_virtual_inr(db, monkeypatch):
    import backend.paper as paper
    import backend.worker as worker

    class FixtureFxProvider:
        def get_quote(self, symbol):
            now = datetime.now(timezone.utc)
            base, quote, price = ("EUR", "USD", 1.08) if symbol == "EUR/USD" else ("USD", "INR", 83.0)
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
    monkeypatch.setattr(worker, "get_market_data_provider", lambda *_args, **_kwargs: provider)
    monkeypatch.setattr(paper, "get_market_data_provider", lambda *_args, **_kwargs: provider)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("STRATEGY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("SIMULATOR_KILL_SWITCH", "false")
    user = configured_user(db, "fx-worker@example.com")
    news = {
        "title": "EUR/USD rises after rate decision",
        "description": "",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "url": "https://news.example/eurusd-rise",
    }

    result = process_strategy_cycle(db, [news], market_open=True)

    assert result["orders"] == 1
    order = db.query(SimulatedOrder).one()
    assert order.market_type == MarketType.FOREX.value
    assert order.symbol == "EUR/USD" and order.base_currency == "EUR"
    assert order.value_inr > order.fill_price * order.quantity
    assert user.portfolio.cash < user.portfolio.starting_cash
