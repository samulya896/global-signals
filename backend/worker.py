"""Opt-in development worker for simulated news-driven orders only.

The worker refuses to execute in production until a production-authorized market-data
provider exists. All fills go through backend.paper.execute_simulated_order.
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR
import hashlib
import logging
import os
import time as sleep_time

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import strategy_worker_enabled, simulator_kill_switch_active
from .database import SessionLocal
from .market_data import MarketType, get_market_data_provider
from .models import SimulatedOrder, StrategyExecution, StrategyVersion, User
from .news import get_live_news
from .paper import (
    FEE_RATE,
    FOREX_FEE_RATE,
    FOREX_SLIPPAGE_RATE,
    MAX_EXPOSURE,
    MAX_ORDER_VALUE,
    SLIPPAGE_RATE,
    _currency_to_inr,
    execute_simulated_order,
    portfolio_snapshot,
)
from .strategy_engine import evaluate_articles


logger = logging.getLogger("global_signals.strategy_worker")
INDIA_TZ = timezone(timedelta(hours=5, minutes=30))
POLL_SECONDS = 10
NEWS_QUERY = "India NSE Nifty OR Sensex OR RBI OR forex OR currency OR USD INR OR EUR USD"


def is_market_session_open(now: datetime | None = None) -> bool:
    """Basic weekday NSE session window in IST; holidays are not modeled."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = current.astimezone(INDIA_TZ)
    return local.weekday() < 5 and time(9, 15) <= local.time().replace(tzinfo=None) < time(15, 30)


def is_forex_session_open(now: datetime | None = None) -> bool:
    """FX composite data is treated as available 24 hours on weekdays only."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(INDIA_TZ).weekday() < 5


def _latest_strategy_versions(db: Session) -> list[StrategyVersion]:
    latest = (
        select(StrategyVersion.user_id, func.max(StrategyVersion.version).label("version"))
        .group_by(StrategyVersion.user_id)
        .subquery()
    )
    return db.scalars(
        select(StrategyVersion).join(
            latest,
            and_(
                StrategyVersion.user_id == latest.c.user_id,
                StrategyVersion.version == latest.c.version,
            ),
        )
    ).all()


def _daily_realized_loss(db: Session, user: User, now: datetime) -> Decimal:
    portfolio_id = user.portfolio.id
    local = now.astimezone(INDIA_TZ)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    value = db.scalar(
        select(func.coalesce(func.sum(SimulatedOrder.realized_pnl), 0)).where(
            SimulatedOrder.portfolio_id == portfolio_id,
            SimulatedOrder.side == "sell",
            SimulatedOrder.created_at >= day_start,
        )
    ) or 0
    return Decimal(str(value))


def _cooldown_active(db: Session, user_id: str, now: datetime, minutes: int) -> bool:
    if minutes <= 0:
        return False
    cutoff = now - timedelta(minutes=minutes)
    recent = db.scalar(
        select(StrategyExecution.id).where(
            StrategyExecution.user_id == user_id,
            StrategyExecution.status == "filled",
            StrategyExecution.created_at >= cutoff,
        ).limit(1)
    )
    return recent is not None


def _record_rejection(db: Session, execution: StrategyExecution, reason: str) -> None:
    execution.status = "rejected"
    execution.reason = reason[:300]
    db.commit()


def _strategy_order_key(signal: dict, symbol: str, side: str) -> str:
    key_hash = hashlib.sha256(f"{signal['article_id']}:{symbol}:{side}".encode("utf-8")).hexdigest()
    return f"strategy-{key_hash[:40]}"


def _submit_signal(db: Session, record: StrategyVersion, user: User, signal: dict, now: datetime) -> dict | None:
    config = record.config
    if _cooldown_active(db, user.id, now, int(config["cooldown_minutes"])):
        return None

    daily_loss_limit = Decimal(str(user.portfolio.starting_cash)) * Decimal(
        str(config["daily_loss_limit_percent"])
    ) / Decimal(100)
    if _daily_realized_loss(db, user, now) <= -daily_loss_limit:
        return None

    market = portfolio_snapshot(db, user)
    if market["equity"] <= 0:
        return None
    holdings = {row["symbol"]: row for row in market["holdings"]}
    market_type = MarketType(signal.get("market_type", MarketType.EQUITY.value))
    provider = get_market_data_provider(market_type)

    for symbol in signal["symbols"]:
        quote = provider.get_quote(symbol)
        conversion, _conversion_time = _currency_to_inr(
            quote.quote_currency,
            now,
            required_at=quote.source_timestamp if market_type is MarketType.FOREX else None,
        )
        holding = holdings.get(symbol)
        if holding and holding.get("market_type", MarketType.EQUITY.value) != market_type.value:
            continue
        if signal["action"] == "SELL":
            quantity = int(holding["quantity"]) if holding else 0
            if quantity <= 0:
                continue
            side = "sell"
            reference_price = quote.bid or quote.price
        elif signal["action"] == "BUY":
            side = "buy"
            reference_price = quote.ask or quote.price
            current_position = Decimal(str(holding["market_value"])) if holding else Decimal(0)
            equity = Decimal(str(market["equity"]))
            position_cap = equity * Decimal(str(config["max_position_percent"])) / Decimal(100)
            portfolio_cap = equity * min(
                MAX_EXPOSURE,
                Decimal(str(config["max_portfolio_exposure_percent"])) / Decimal(100),
            )
            remaining = min(
                position_cap - current_position,
                portfolio_cap - Decimal(str(market["market_value"])),
                MAX_ORDER_VALUE,
                Decimal(str(market["cash"])),
            )
            fee_rate = FOREX_FEE_RATE if market_type is MarketType.FOREX else FEE_RATE
            slippage_rate = FOREX_SLIPPAGE_RATE if market_type is MarketType.FOREX else SLIPPAGE_RATE
            unit_cost = Decimal(str(reference_price)) * conversion * (1 + slippage_rate) * (1 + fee_rate)
            quantity = int((remaining / unit_cost).to_integral_value(rounding=ROUND_FLOOR)) if remaining > 0 else 0
            if quantity <= 0:
                continue
        else:
            continue

        return execute_simulated_order(
            db,
            user,
            symbol,
            side,
            quantity,
            _strategy_order_key(signal, symbol, side),
            market_type=market_type,
        )
    return None


def process_strategy_cycle(
    db: Session,
    articles: list[dict],
    *,
    now: datetime | None = None,
    market_open: bool | None = None,
) -> dict[str, int | str]:
    """Evaluate enabled account rules and create paper fills, with persistent deduplication."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    if os.getenv("APP_ENV", "development").strip().lower() != "development":
        return {"status": "disabled_outside_development", "orders": 0, "duplicates": 0, "rejected": 0}
    if not strategy_worker_enabled() or simulator_kill_switch_active():
        return {"status": "disabled_by_global_switch", "orders": 0, "duplicates": 0, "rejected": 0}
    if not (is_forex_session_open(current) if market_open is None else market_open):
        return {"status": "market_closed", "orders": 0, "duplicates": 0, "rejected": 0}

    summary = {"status": "processed", "orders": 0, "duplicates": 0, "rejected": 0}
    for record in _latest_strategy_versions(db):
        config = record.config
        if not config.get("enabled", False):
            continue
        user = db.get(User, record.user_id)
        if user is None or user.portfolio is None:
            continue
        for signal in evaluate_articles(articles, config, now=current):
            if not signal["accepted"]:
                continue
            if signal.get("market_type", MarketType.EQUITY.value) == MarketType.EQUITY.value:
                if not (is_market_session_open(current) if market_open is None else market_open):
                    continue
            if simulator_kill_switch_active():
                summary["status"] = "stopped_by_kill_switch"
                return summary
            existing = db.scalar(
                select(StrategyExecution).where(
                    StrategyExecution.user_id == user.id,
                    StrategyExecution.article_id == signal["article_id"],
                )
            )
            if existing and existing.status != "processing":
                summary["duplicates"] += 1
                continue
            if existing:
                # A prior worker may have stopped after recording the claim. The order
                # service's persistent idempotency key makes retrying this state safe.
                execution = existing
            else:
                execution = StrategyExecution(
                    user_id=user.id,
                    article_id=signal["article_id"],
                    strategy_version=record.version,
                    status="processing",
                    reason="Accepted by configured news rules; risk checks are pending.",
                )
                db.add(execution)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    summary["duplicates"] += 1
                    continue
                db.refresh(execution)

            try:
                committed_order = None
                side = "sell" if signal["action"] == "SELL" else "buy"
                for symbol in signal["symbols"]:
                    committed_order = db.scalar(
                        select(SimulatedOrder).where(
                            SimulatedOrder.portfolio_id == user.portfolio.id,
                            SimulatedOrder.idempotency_key == _strategy_order_key(signal, symbol, side),
                        )
                    )
                    if committed_order is not None:
                        break
                order = committed_order or _submit_signal(db, record, user, signal, current)
                if order is not None:
                    execution.status = "filled"
                    execution.reason = "Simulated order filled by the paper-trading service."
                    execution.simulated_order_id = order["id"]
                    summary["orders"] += 1
                else:
                    execution.status = "rejected"
                    execution.reason = "Risk, cooldown, daily-loss, position, or buying-power control rejected the order."
                    summary["rejected"] += 1
                db.commit()
            except Exception:
                db.rollback()
                execution = db.get(StrategyExecution, execution.id)
                if execution is not None:
                    reconciled_order = None
                    for symbol in signal["symbols"]:
                        side = "sell" if signal["action"] == "SELL" else "buy"
                        reconciled_order = db.scalar(
                            select(SimulatedOrder).where(
                                SimulatedOrder.portfolio_id == user.portfolio.id,
                                SimulatedOrder.idempotency_key == _strategy_order_key(signal, symbol, side),
                            )
                        )
                        if reconciled_order is not None:
                            break
                    if reconciled_order is not None:
                        execution.status = "filled"
                        execution.simulated_order_id = reconciled_order.id
                        execution.reason = "Recovered a committed simulated fill after a worker error."
                        db.commit()
                        summary["orders"] += 1
                    else:
                        _record_rejection(db, execution, "Execution failed; no successful paper fill was confirmed.")
                        summary["rejected"] += 1
                else:
                    summary["rejected"] += 1
    return summary


def run_worker() -> None:
    logger.info("Global Signals paper strategy worker started; broker execution is not implemented.")
    if os.getenv("APP_ENV", "development").strip().lower() != "development":
        logger.error("Worker execution is disabled outside development; exiting without submitting orders.")
        return
    while True:
        if not strategy_worker_enabled() or simulator_kill_switch_active():
            sleep_time.sleep(POLL_SECONDS)
            continue
        if not is_forex_session_open():
            sleep_time.sleep(POLL_SECONDS)
            continue
        try:
            articles = get_live_news(query=NEWS_QUERY, page_size=20)
            with SessionLocal() as db:
                summary = process_strategy_cycle(db, articles)
            logger.info("Strategy cycle finished: status=%s orders=%s duplicates=%s rejected=%s", *summary.values())
        except Exception:
            logger.error("Strategy worker cycle failed; sensitive provider values were not logged.")
        sleep_time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    run_worker()
