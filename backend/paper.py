"""One persistent INR paper ledger for both Indian equities and currency pairs."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import os
import threading

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .database import IS_SQLITE
from .config import SETTINGS, simulator_kill_switch_active
from .market_data import (
    DataStatus,
    MarketDataError,
    MarketType,
    NormalizedQuote,
    SyntheticDemoProvider,
    get_market_data_provider,
)
from .models import AuditEvent, PortfolioSnapshot, SimulatedOrder, User, VirtualPortfolio, VirtualPosition
from .simulator import SYMBOLS


CENT = Decimal("0.01")
FEE_RATE = SETTINGS.fee_bps / Decimal(10_000)
SLIPPAGE_RATE = SETTINGS.slippage_bps / Decimal(10_000)
FOREX_FEE_RATE = SETTINGS.forex_fee_bps / Decimal(10_000)
FOREX_SLIPPAGE_RATE = SETTINGS.forex_slippage_bps / Decimal(10_000)
MAX_ORDER_VALUE = SETTINGS.max_order_value
MAX_EXPOSURE = SETTINGS.max_exposure_percent / Decimal(100)
SQLITE_TRADE_LOCK = threading.RLock()


def dec(value) -> Decimal:
    return Decimal(str(value))


def ensure_portfolio(db: Session, user: User) -> VirtualPortfolio:
    portfolio = db.scalar(select(VirtualPortfolio).where(VirtualPortfolio.user_id == user.id))
    if portfolio is None:
        raise HTTPException(status_code=500, detail="Paper portfolio is not initialized.")
    return portfolio


def _provider(market_type: MarketType, *, allow_demo: bool = True):
    try:
        return get_market_data_provider(market_type, allow_demo=allow_demo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported market type.") from exc


def _as_http_error(exc: MarketDataError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _quote_for(provider, symbol: str) -> NormalizedQuote:
    try:
        return provider.get_quote(symbol)
    except MarketDataError as exc:
        raise _as_http_error(exc) from exc


def _timestamp_age(timestamp: datetime, now: datetime) -> float:
    if timestamp.tzinfo is None:
        raise HTTPException(status_code=503, detail="Market data timestamp is missing a timezone.")
    age = (now - timestamp.astimezone(timezone.utc)).total_seconds()
    if age < -5:
        raise HTTPException(status_code=503, detail="Market data timestamp is in the future.")
    return age


def _require_fresh_quote(quote: NormalizedQuote, now: datetime, *, order: bool) -> None:
    if quote.metadata.get("synthetic"):
        if os.getenv("APP_ENV", "development").strip().lower() != "development":
            raise HTTPException(status_code=503, detail="Synthetic demo data is unavailable outside development.")
        return
    max_age = 120 if quote.market_type is MarketType.FOREX else 90
    age = _timestamp_age(quote.source_timestamp, now)
    if quote.status is not DataStatus.LIVE or age > max_age:
        message = "A fresh quote is required before submitting a simulated order." if order else "Market quote is stale or unavailable."
        raise HTTPException(status_code=503, detail=message)
    if quote.market_type is MarketType.EQUITY and quote.market_status != "NORMAL_OPEN" and order:
        raise HTTPException(status_code=409, detail="The selected exchange is closed; no paper fill was created.")


def _currency_to_inr(currency: str, now: datetime, *, required_at: datetime | None = None) -> tuple[Decimal, datetime]:
    currency = currency.upper()
    if currency == "INR":
        stamp = required_at or now
        return Decimal("1"), stamp.astimezone(timezone.utc)

    provider = _provider(MarketType.FOREX, allow_demo=False)
    failures: list[MarketDataError] = []
    for pair, inverted in ((f"{currency}/INR", False), (f"INR/{currency}", True)):
        try:
            quote = _quote_for(provider, pair)
            _require_fresh_quote(quote, now, order=True)
            if quote.market_type is not MarketType.FOREX:
                raise HTTPException(status_code=503, detail="Currency conversion provider returned the wrong market type.")
            if required_at and abs((quote.source_timestamp - required_at).total_seconds()) > 120:
                raise HTTPException(status_code=503, detail="Currency conversion quote does not align with the trade quote timestamp.")
            rate = dec(quote.price)
            return (Decimal("1") / rate if inverted else rate), quote.source_timestamp
        except HTTPException as exc:
            if exc.status_code not in {404, 422, 502, 503}:
                raise
            failures.append(MarketDataError(str(exc.detail), exc.status_code))
    raise HTTPException(
        status_code=503,
        detail=f"A fresh timestamped {currency}/INR conversion rate is unavailable; the paper order was not created.",
    ) from (failures[-1] if failures else None)


def _price_tick(quote: NormalizedQuote) -> Decimal:
    if quote.market_type is MarketType.FOREX:
        return Decimal("0.001") if quote.quote_currency == "JPY" else Decimal("0.00001")
    tick = quote.metadata.get("tick_size")
    try:
        value = Decimal(str(tick)) if tick is not None else Decimal("0.01")
        # Upstox's instrument master reports some tick sizes in paise (e.g. 5 => ₹0.05).
        if value > Decimal("1"):
            value /= Decimal("100")
        return value if value > 0 else Decimal("0.01")
    except Exception:
        return Decimal("0.01")


def _round_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    return (value / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick


def _price_digits(quote_currency: str, market_type: str) -> int:
    if market_type == MarketType.EQUITY.value:
        return 2
    return 3 if quote_currency == "JPY" else 5


def _holdings(db: Session, portfolio_id: str, now: datetime | None = None):
    current = now or datetime.now(timezone.utc)
    positions = db.scalars(
        select(VirtualPosition).where(VirtualPosition.portfolio_id == portfolio_id).order_by(VirtualPosition.symbol)
    ).all()
    rows = []
    market_value_inr = Decimal("0")
    unrealized_inr = Decimal("0")
    for position in positions:
        market = MarketType(position.market_type)
        quote = _quote_for(_provider(market), position.symbol)
        _require_fresh_quote(quote, current, order=False)
        conversion, conversion_timestamp = _currency_to_inr(
            position.quote_currency, current, required_at=quote.source_timestamp if market is MarketType.FOREX else None
        )
        quantity = position.quantity
        market_value_quote = dec(quote.price) * quantity
        value_inr = market_value_quote * conversion
        average_entry_inr = dec(position.average_entry_inr or position.average_entry)
        pnl_inr = value_inr - average_entry_inr * quantity
        market_value_inr += value_inr
        unrealized_inr += pnl_inr
        digits = _price_digits(position.quote_currency, position.market_type)
        rows.append({
            "market_type": position.market_type,
            "symbol": position.symbol,
            "quantity": quantity,
            "quantity_unit": position.base_currency if market is MarketType.FOREX else "shares",
            "base_currency": position.base_currency,
            "quote_currency": position.quote_currency,
            "average_cost": round(float(position.average_entry), digits),
            "average_cost_inr": float(average_entry_inr.quantize(CENT)),
            "price": round(float(quote.price), digits),
            "price_basis": quote.price_basis,
            "provider": quote.provider,
            "source_timestamp": quote.source_timestamp.isoformat(),
            "data_status": quote.status.value,
            "conversion_rate_to_inr": float(conversion),
            "conversion_timestamp": conversion_timestamp.isoformat(),
            "market_value_quote": round(float(market_value_quote), digits),
            "market_value": float(value_inr.quantize(CENT)),
            "unrealized_pnl": float(pnl_inr.quantize(CENT)),
        })
    return rows, market_value_inr, unrealized_inr


def portfolio_snapshot(db: Session, user: User) -> dict:
    portfolio = ensure_portfolio(db, user)
    holdings, market_value, unrealized = _holdings(db, portfolio.id)
    orders = db.scalars(
        select(SimulatedOrder)
        .where(SimulatedOrder.portfolio_id == portfolio.id)
        .order_by(SimulatedOrder.created_at.desc())
        .limit(10)
    ).all()
    realized_total = db.scalar(select(func.coalesce(func.sum(SimulatedOrder.realized_pnl), 0)).where(
        SimulatedOrder.portfolio_id == portfolio.id,
        SimulatedOrder.side == "sell",
    )) or Decimal("0")
    return {
        "mode": "simulation",
        "currency": "INR",
        "starting_cash": float(portfolio.starting_cash),
        "cash": float(portfolio.cash),
        "market_value": float(market_value.quantize(CENT)),
        "equity": float((portfolio.cash + market_value).quantize(CENT)),
        "realized_pnl": float(dec(realized_total).quantize(CENT)),
        "unrealized_pnl": float(unrealized.quantize(CENT)),
        "valuation_complete": True,
        "holdings": holdings,
        "recent_trades": [serialize_order(order) for order in orders],
    }


def serialize_order(order: SimulatedOrder) -> dict:
    created_at = order.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    source_timestamp = order.source_timestamp
    if source_timestamp is not None and source_timestamp.tzinfo is None:
        source_timestamp = source_timestamp.replace(tzinfo=timezone.utc)
    digits = _price_digits(order.quote_currency, order.market_type)
    result = {
        "id": order.id,
        "market_type": order.market_type,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "quantity_unit": order.base_currency if order.market_type == MarketType.FOREX.value else "shares",
        "base_currency": order.base_currency,
        "quote_currency": order.quote_currency,
        "price": round(float(order.fill_price), digits),
        "quote_price": round(float(order.quote_price), digits),
        "bid": round(float(order.bid), digits) if order.bid is not None else None,
        "ask": round(float(order.ask), digits) if order.ask is not None else None,
        "price_basis": order.price_basis,
        "provider": order.source_provider,
        "source_timestamp": source_timestamp.isoformat() if source_timestamp else None,
        "conversion_rate_to_inr": float(order.conversion_rate),
        "value": round(float(order.fill_price * order.quantity), digits),
        "value_inr": float(order.value_inr.quantize(CENT)),
        "fees": float(order.fees.quantize(CENT)),
        "slippage": float(order.slippage.quantize(CENT)),
        "realized_pnl": float(order.realized_pnl.quantize(CENT)),
        "timestamp": created_at.isoformat(),
        "status": order.status,
        "mode": "simulation",
    }
    return result


def _request_fingerprint(market: MarketType, symbol: str, side: str, quantity: int) -> str:
    encoded = json.dumps([market.value, symbol.strip().upper(), side, quantity], separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def execute_simulated_order(
    db: Session,
    user: User,
    symbol: str,
    side: str,
    quantity: int,
    idempotency_key: str,
    *,
    market_type: MarketType | str = MarketType.EQUITY,
) -> dict:
    """Create a virtual fill in INR; never contacts a broker or submits a real order."""
    if simulator_kill_switch_active():
        raise HTTPException(status_code=503, detail="The global paper-simulator kill switch is active.")
    try:
        market = market_type if isinstance(market_type, MarketType) else MarketType(str(market_type).upper())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported market type.") from exc
    symbol = symbol.strip().upper()
    if side not in ("buy", "sell") or not isinstance(quantity, int) or quantity <= 0:
        raise HTTPException(status_code=422, detail="Invalid simulated order parameters.")
    if not idempotency_key or len(idempotency_key) > 80:
        raise HTTPException(status_code=400, detail="A valid idempotency key is required.")

    fingerprint = _request_fingerprint(market, symbol, side, quantity)
    portfolio = ensure_portfolio(db, user)
    existing = db.scalar(select(SimulatedOrder).where(
        SimulatedOrder.portfolio_id == portfolio.id,
        SimulatedOrder.idempotency_key == idempotency_key,
    ))
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key was already used for a different order.")
        db.commit()
        return serialize_order(existing)
    db.commit()

    provider = _provider(market)
    quote = _quote_for(provider, symbol)
    now = datetime.now(timezone.utc)
    _require_fresh_quote(quote, now, order=True)
    if market is MarketType.EQUITY and quote.quote_currency != "INR":
        raise HTTPException(status_code=422, detail="Only INR-denominated Indian equities are supported by this portfolio.")
    if market is MarketType.FOREX and (not quote.base_currency or not quote.quote_currency):
        raise HTTPException(status_code=502, detail="Forex provider omitted base or quote currency metadata.")
    conversion, conversion_timestamp = _currency_to_inr(
        quote.quote_currency, now, required_at=quote.source_timestamp if market is MarketType.FOREX else None
    )

    # For equities, size is shares. For FX, size is integer units of the pair's base currency.
    reference_price = dec(quote.ask if side == "buy" and quote.ask else quote.bid if side == "sell" and quote.bid else quote.price)
    fee_rate = FOREX_FEE_RATE if market is MarketType.FOREX else FEE_RATE
    slippage_rate = FOREX_SLIPPAGE_RATE if market is MarketType.FOREX else SLIPPAGE_RATE
    tick = _price_tick(quote)
    fill_price = _round_to_tick(reference_price * (Decimal("1") + slippage_rate if side == "buy" else Decimal("1") - slippage_rate), tick)
    if fill_price <= 0:
        raise HTTPException(status_code=422, detail="Simulated fill price is invalid.")
    gross_quote = fill_price * quantity
    gross_inr = gross_quote * conversion
    if gross_inr > MAX_ORDER_VALUE:
        raise HTTPException(status_code=400, detail=f"Order exceeds the virtual INR order limit of ₹{MAX_ORDER_VALUE}.")
    fee = (gross_inr * fee_rate).quantize(CENT, rounding=ROUND_HALF_UP)
    slippage = (abs(fill_price - reference_price) * quantity * conversion).quantize(CENT, rounding=ROUND_HALF_UP)

    lock = SQLITE_TRADE_LOCK if IS_SQLITE else _NullLock()
    with lock:
        try:
            if IS_SQLITE:
                db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            now = datetime.now(timezone.utc)
            _require_fresh_quote(quote, now, order=True)
            if market is MarketType.FOREX:
                conversion_age = _timestamp_age(conversion_timestamp, now)
                if conversion_age > 120:
                    raise HTTPException(status_code=503, detail="A fresh currency conversion rate is required for this simulated order.")
            portfolio = db.scalar(
                select(VirtualPortfolio).where(VirtualPortfolio.user_id == user.id).with_for_update()
            )
            if portfolio is None:
                raise HTTPException(status_code=500, detail="Paper portfolio is not initialized.")
            previous = db.scalar(select(SimulatedOrder).where(
                SimulatedOrder.portfolio_id == portfolio.id,
                SimulatedOrder.idempotency_key == idempotency_key,
            ))
            if previous:
                if previous.request_fingerprint != fingerprint:
                    raise HTTPException(status_code=409, detail="Idempotency key was already used for a different order.")
                db.commit()
                return serialize_order(previous)

            symbol = quote.symbol
            if isinstance(provider, SyntheticDemoProvider) and symbol not in SYMBOLS:
                raise HTTPException(status_code=400, detail="Symbol is not in the local synthetic demo universe.")
            position = db.scalar(select(VirtualPosition).where(
                VirtualPosition.portfolio_id == portfolio.id,
                VirtualPosition.symbol == symbol,
            ).with_for_update())
            realized = Decimal("0")

            if side == "buy":
                required_cash = gross_inr + fee
                if required_cash > portfolio.cash:
                    raise HTTPException(status_code=400, detail="Insufficient virtual INR cash including costs and conversion.")
                holdings, market_value, _unrealized = _holdings(db, portfolio.id, now)
                equity_before = dec(portfolio.cash) + market_value
                if market_value + gross_inr > equity_before * MAX_EXPOSURE:
                    raise HTTPException(status_code=400, detail="Order exceeds the configured virtual portfolio exposure limit.")
                old_qty = position.quantity if position else 0
                old_quote_cost = position.average_entry if position else Decimal("0")
                old_inr_cost = position.average_entry_inr or old_quote_cost if position else Decimal("0")
                new_qty = old_qty + quantity
                fee_quote = fee / conversion
                average_entry = (old_quote_cost * old_qty + gross_quote + fee_quote) / new_qty
                average_entry_inr = (dec(old_inr_cost) * old_qty + gross_inr + fee) / new_qty
                if position:
                    if position.market_type != market.value or position.quote_currency != quote.quote_currency:
                        raise HTTPException(status_code=409, detail="Existing position metadata conflicts with the selected market.")
                    position.quantity = new_qty
                    position.average_entry = average_entry
                    position.average_entry_inr = average_entry_inr
                else:
                    position = VirtualPosition(
                        portfolio_id=portfolio.id,
                        market_type=market.value,
                        symbol=symbol,
                        quantity=new_qty,
                        base_currency=quote.base_currency,
                        quote_currency=quote.quote_currency,
                        average_entry=average_entry,
                        average_entry_inr=average_entry_inr,
                    )
                    db.add(position)
                portfolio.cash = dec(portfolio.cash) - required_cash
            else:
                if position is None or quantity > position.quantity:
                    unit_name = quote.base_currency if market is MarketType.FOREX else "shares"
                    raise HTTPException(status_code=400, detail=f"Cannot sell more {unit_name} than the portfolio holds.")
                net_proceeds_inr = gross_inr - fee
                average_entry_inr = dec(position.average_entry_inr or position.average_entry)
                realized = net_proceeds_inr - average_entry_inr * quantity
                position.quantity -= quantity
                if position.quantity == 0:
                    db.delete(position)
                portfolio.cash = dec(portfolio.cash) + net_proceeds_inr

            order = SimulatedOrder(
                portfolio_id=portfolio.id,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                market_type=market.value,
                symbol=symbol,
                side=side,
                quantity=quantity,
                base_currency=quote.base_currency,
                quote_currency=quote.quote_currency,
                quote_price=reference_price,
                fill_price=fill_price,
                conversion_rate=conversion,
                value_inr=gross_inr.quantize(CENT, rounding=ROUND_HALF_UP),
                source_provider=quote.provider,
                price_basis=quote.price_basis,
                source_timestamp=quote.source_timestamp,
                bid=dec(quote.bid) if quote.bid is not None else None,
                ask=dec(quote.ask) if quote.ask is not None else None,
                fees=fee,
                slippage=slippage,
                realized_pnl=realized,
                status="filled",
                mode="simulation",
            )
            db.add(order)
            db.flush()
            db.add(AuditEvent(user_id=user.id, event_type="simulated_order_filled", object_id=order.id))
            _new_holdings, market_value_after, _unrealized_after = _holdings(db, portfolio.id, now)
            db.add(PortfolioSnapshot(
                portfolio_id=portfolio.id,
                cash=portfolio.cash,
                market_value=market_value_after,
                equity=dec(portfolio.cash) + market_value_after,
            ))
            db.commit()
            db.refresh(order)
            return serialize_order(order)
        except Exception:
            db.rollback()
            raise


def performance(db: Session, user: User) -> dict:
    state = portfolio_snapshot(db, user)
    portfolio = ensure_portfolio(db, user)
    total_realized = db.scalar(select(func.coalesce(func.sum(SimulatedOrder.realized_pnl), 0)).where(
        SimulatedOrder.portfolio_id == portfolio.id,
        SimulatedOrder.side == "sell",
    )) or Decimal("0")
    return {
        "mode": "simulation",
        "currency": "INR",
        "starting_cash": state["starting_cash"],
        "equity": state["equity"],
        "total_return": round((state["equity"] / state["starting_cash"] - 1) * 100, 2),
        "realized_pnl": float(dec(total_realized).quantize(CENT)),
        "unrealized_pnl": state["unrealized_pnl"],
        "trade_count": db.scalar(select(func.count(SimulatedOrder.id)).where(
            SimulatedOrder.portfolio_id == portfolio.id,
        )) or 0,
    }


def portfolio_history(db: Session, user: User) -> list[dict]:
    portfolio = ensure_portfolio(db, user)
    snapshots = db.scalars(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.portfolio_id == portfolio.id)
        .order_by(PortfolioSnapshot.recorded_at.desc())
        .limit(365)
    ).all()
    points = []
    for item in reversed(snapshots):
        recorded_at = item.recorded_at
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        points.append({"recorded_at": recorded_at.isoformat(), "equity": float(item.equity)})
    return points


def reset_portfolio(db: Session, user: User) -> dict:
    lock = SQLITE_TRADE_LOCK if IS_SQLITE else _NullLock()
    with lock:
        try:
            if IS_SQLITE:
                db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            portfolio = db.scalar(
                select(VirtualPortfolio).where(VirtualPortfolio.user_id == user.id).with_for_update()
            )
            if portfolio is None:
                raise HTTPException(status_code=500, detail="Paper portfolio is not initialized.")
            db.execute(delete(SimulatedOrder).where(SimulatedOrder.portfolio_id == portfolio.id))
            db.execute(delete(VirtualPosition).where(VirtualPosition.portfolio_id == portfolio.id))
            db.execute(delete(PortfolioSnapshot).where(PortfolioSnapshot.portfolio_id == portfolio.id))
            portfolio.cash = portfolio.starting_cash
            db.add(AuditEvent(user_id=user.id, event_type="virtual_portfolio_reset", object_id=portfolio.id))
            db.add(PortfolioSnapshot(
                portfolio_id=portfolio.id,
                cash=portfolio.starting_cash,
                market_value=Decimal("0"),
                equity=portfolio.starting_cash,
            ))
            db.commit()
            return portfolio_snapshot(db, user)
        except Exception:
            db.rollback()
            raise


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False
