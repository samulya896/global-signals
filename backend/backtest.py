"""Deterministic, in-memory replay of user-supplied historical market and news data.

This module never contacts a market provider, changes a stored paper portfolio, or
submits an order. Signals become eligible only after their publication time and
can fill only at a later candle's open.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

from .config import SETTINGS
from .schemas import HistoricalBacktestRequest, HistoricalCandleInput
from .strategy_engine import DEFAULT_STRATEGY_CONFIG, evaluate_articles


CENT = Decimal("0.01")
MAX_FX_AGE = timedelta(hours=24)
MAX_PRICE_GAP = timedelta(days=7)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("All historical timestamps must include a timezone.")
    return value.astimezone(timezone.utc)


def _instrument_key(market_type: str, symbol: str) -> tuple[str, str]:
    return market_type.upper(), symbol.strip().upper()


def _round_price(value: Decimal, market_type: str, quote_currency: str) -> Decimal:
    digits = 2 if market_type == "EQUITY" else (3 if quote_currency == "JPY" else 5)
    step = Decimal(1).scaleb(-digits)
    return (value / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step


def _fx_rate(
    currency: str,
    at: datetime,
    current_open_rates: dict[tuple[str, str], tuple[datetime, Decimal]],
    latest_close_rates: dict[tuple[str, str], tuple[datetime, Decimal]],
) -> Decimal | None:
    currency = currency.upper()
    if currency == "INR":
        return Decimal("1")
    for key, inverted in (((currency, "INR"), False), (("INR", currency), True)):
        rate = current_open_rates.get(key) or latest_close_rates.get(key)
        if rate is None:
            continue
        stamp, value = rate
        if stamp > at or at - stamp > MAX_FX_AGE or value <= 0:
            continue
        return Decimal("1") / value if inverted else value
    return None


def _latest_price(
    candle: HistoricalCandleInput,
    side: str,
) -> Decimal:
    return _decimal(getattr(candle, side))


def replay_backtest(
    request: HistoricalBacktestRequest,
    strategy_config: dict[str, int | float] | None = None,
    *,
    strategy_version: int = 0,
) -> dict[str, Any]:
    """Replay news decisions and virtual fills against supplied chronological bars."""
    config = {**DEFAULT_STRATEGY_CONFIG, **(strategy_config or {})}
    candles_by_time: dict[datetime, list[HistoricalCandleInput]] = defaultdict(list)
    bars_by_instrument: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    for candle in request.candles:
        stamp = _utc(candle.timestamp)
        key = _instrument_key(candle.market_type, candle.symbol)
        candles_by_time[stamp].append(candle)
        bars_by_instrument[key].append(stamp)

    for values in bars_by_instrument.values():
        values.sort()
    timeline = sorted(candles_by_time)
    if len(timeline) < 2:
        raise ValueError("At least two distinct chronological timestamps are required.")

    news = sorted(request.news, key=lambda item: _utc(item.published_at))
    news_index = 0
    seen_articles: set[str] = set()
    latest_close_rates: dict[tuple[str, str], tuple[datetime, Decimal]] = {}
    latest_prices: dict[tuple[str, str], tuple[datetime, Decimal, HistoricalCandleInput]] = {}
    current_open_rates: dict[tuple[str, str], tuple[datetime, Decimal]] = {}
    positions: dict[tuple[str, str], dict[str, Any]] = {}
    cash = _decimal(request.starting_cash)
    fee_rate_equity = SETTINGS.fee_bps / Decimal(10_000)
    slip_rate_equity = SETTINGS.slippage_bps / Decimal(10_000)
    fee_rate_fx = SETTINGS.forex_fee_bps / Decimal(10_000)
    slip_rate_fx = SETTINGS.forex_slippage_bps / Decimal(10_000)
    order_limit = SETTINGS.max_order_value
    exposure_limit = SETTINGS.max_exposure_percent / Decimal(100)
    last_fill_at: datetime | None = None
    daily_realized: dict[str, Decimal] = defaultdict(Decimal)
    decisions: list[dict[str, Any]] = []
    pending: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    trades: list[dict[str, Any]] = []
    total_fills = 0
    equity_curve: list[dict[str, Any]] = []
    realized_total = Decimal("0")
    fees_total = Decimal("0")
    slippage_total = Decimal("0")
    max_drawdown = Decimal("0")
    peak_equity = cash

    def mark_portfolio(at: datetime) -> tuple[Decimal, Decimal]:
        market_value = Decimal("0")
        for key, position in positions.items():
            latest = latest_prices.get(key)
            if latest is None:
                raise ValueError(f"Historical candles do not cover the open position {key[1]}.")
            price_time, price, candle = latest
            if at - price_time > MAX_PRICE_GAP:
                raise ValueError(f"Historical price for open position {key[1]} is missing for more than seven days.")
            conversion = _fx_rate(candle.quote_currency, at, current_open_rates, latest_close_rates)
            if conversion is None:
                raise ValueError(
                    f"The dataset lacks a fresh {candle.quote_currency}/INR conversion candle needed to value {key[1]}."
                )
            market_value += position["quantity"] * price * conversion
        equity = cash + market_value
        return market_value, equity

    for stamp in timeline:
        bars = sorted(
            candles_by_time[stamp],
            key=lambda row: (row.market_type, row.symbol.upper()),
        )
        current_open_rates = {}
        for candle in bars:
            if candle.market_type == "FOREX":
                fx_key = (candle.base_currency or "", candle.quote_currency)
                current_open_rates[fx_key] = (stamp, _latest_price(candle, "open"))

        # Only decisions queued at an earlier replay time can fill at this open.
        for candle in bars:
            instrument = _instrument_key(candle.market_type, candle.symbol)
            queued = pending.pop(instrument, [])
            for item in queued:
                decision = item["decision"]
                side = "buy" if decision["action"] == "BUY" else "sell"
                market_type = candle.market_type
                quote_currency = candle.quote_currency
                base_currency = candle.base_currency
                fx_rate = _fx_rate(quote_currency, stamp, current_open_rates, latest_close_rates)
                if fx_rate is None:
                    decision["status"] = "rejected"
                    decision["reason"] = f"No fresh {quote_currency}/INR conversion candle was available at the next open."
                    continue

                position = positions.get(instrument)
                if position and (position["market_type"] != market_type or position["quote_currency"] != quote_currency):
                    decision["status"] = "rejected"
                    decision["reason"] = "Historical candle metadata conflicts with the open position."
                    continue

                if last_fill_at and (stamp - last_fill_at).total_seconds() < int(config["cooldown_minutes"]) * 60:
                    decision["status"] = "rejected"
                    decision["reason"] = "Configured strategy cooldown is active."
                    continue
                day_key = stamp.astimezone(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
                daily_limit = _decimal(request.starting_cash) * _decimal(config["daily_loss_limit_percent"]) / Decimal(100)
                if daily_realized[day_key] <= -daily_limit:
                    decision["status"] = "rejected"
                    decision["reason"] = "Configured daily realized-loss limit is active."
                    continue

                if side == "sell":
                    quantity = min(position["quantity"], 10_000_000) if position else 0
                    if quantity <= 0:
                        decision["status"] = "rejected"
                        decision["reason"] = "The strategy returned SELL, but the virtual portfolio holds no units; short selling is disabled."
                        continue
                else:
                    _, equity_before = mark_portfolio(stamp)
                    if equity_before <= 0:
                        decision["status"] = "rejected"
                        decision["reason"] = "Portfolio equity is not positive."
                        continue
                    market_value_before = equity_before - cash
                    current_position_value = Decimal("0")
                    if position:
                        previous = latest_prices.get(instrument)
                        if previous is not None:
                            prev_time, prev_price, prev_candle = previous
                            prev_fx = _fx_rate(prev_candle.quote_currency, stamp, current_open_rates, latest_close_rates)
                            if prev_fx is not None:
                                current_position_value = position["quantity"] * prev_price * prev_fx
                    position_cap = equity_before * _decimal(config["max_position_percent"]) / Decimal(100)
                    portfolio_cap = equity_before * min(
                        exposure_limit,
                        _decimal(config["max_portfolio_exposure_percent"]) / Decimal(100),
                    )
                    remaining = min(
                        position_cap - current_position_value,
                        portfolio_cap - market_value_before,
                        order_limit,
                        cash,
                    )
                    fee_rate = fee_rate_fx if market_type == "FOREX" else fee_rate_equity
                    slip_rate = slip_rate_fx if market_type == "FOREX" else slip_rate_equity
                    raw_open = _latest_price(candle, "open")
                    fill_price = _round_price(raw_open * (Decimal(1) + slip_rate), market_type, quote_currency)
                    unit_cost_inr = fill_price * fx_rate * (Decimal(1) + fee_rate)
                    quantity = int((remaining / unit_cost_inr).to_integral_value(rounding=ROUND_FLOOR)) if remaining > 0 else 0
                    if quantity <= 0:
                        decision["status"] = "rejected"
                        decision["reason"] = "Position, portfolio exposure, order value, or cash risk limit allowed no whole units."
                        continue

                raw_open = _latest_price(candle, "open")
                fee_rate = fee_rate_fx if market_type == "FOREX" else fee_rate_equity
                slip_rate = slip_rate_fx if market_type == "FOREX" else slip_rate_equity
                fill_price = _round_price(
                    raw_open * (Decimal(1) + slip_rate if side == "buy" else Decimal(1) - slip_rate),
                    market_type,
                    quote_currency,
                )
                if fill_price <= 0:
                    decision["status"] = "rejected"
                    decision["reason"] = "Slippage produced a nonpositive virtual fill price."
                    continue
                gross_inr = fill_price * quantity * fx_rate
                if side == "sell" and gross_inr > order_limit:
                    quantity = min(
                        quantity,
                        int((order_limit / (fill_price * fx_rate)).to_integral_value(rounding=ROUND_FLOOR)),
                    )
                    if quantity <= 0:
                        decision["status"] = "rejected"
                        decision["reason"] = "The virtual order-value limit allowed no whole units to sell."
                        continue
                    gross_inr = fill_price * quantity * fx_rate
                if gross_inr > order_limit:
                    decision["status"] = "rejected"
                    decision["reason"] = "The virtual order exceeds the configured INR order-value limit."
                    continue
                fee = (gross_inr * fee_rate).quantize(CENT, rounding=ROUND_HALF_UP)
                slippage = (abs(fill_price - raw_open) * quantity * fx_rate).quantize(CENT, rounding=ROUND_HALF_UP)
                realized = Decimal("0")
                if side == "buy":
                    if quantity > 10_000_000:
                        decision["status"] = "rejected"
                        decision["reason"] = "The virtual order exceeds the simulator's 10,000,000-unit limit."
                        continue
                    if gross_inr + fee > cash:
                        decision["status"] = "rejected"
                        decision["reason"] = "Insufficient virtual INR cash after fees."
                        continue
                    old_quantity = position["quantity"] if position else 0
                    old_cost = position["average_entry_inr"] * old_quantity if position else Decimal("0")
                    new_quantity = old_quantity + quantity
                    average_inr = (old_cost + gross_inr + fee) / new_quantity
                    positions[instrument] = {
                        "quantity": new_quantity,
                        "average_entry_inr": average_inr,
                        "market_type": market_type,
                        "base_currency": base_currency,
                        "quote_currency": quote_currency,
                    }
                    cash -= gross_inr + fee
                else:
                    if position is None or quantity > position["quantity"]:
                        decision["status"] = "rejected"
                        decision["reason"] = "The requested virtual sale exceeds held units; short selling is disabled."
                        continue
                    proceeds = gross_inr - fee
                    realized = proceeds - position["average_entry_inr"] * quantity
                    position["quantity"] -= quantity
                    cash += proceeds
                    if position["quantity"] == 0:
                        del positions[instrument]
                    day_key = stamp.astimezone(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
                    daily_realized[day_key] += realized
                    realized_total += realized
                last_fill_at = stamp
                fees_total += fee
                slippage_total += slippage
                decision["status"] = "filled"
                decision["reason"] = "Filled virtually at the next candle open with configured slippage and fees."
                decision["fill_timestamp"] = stamp.isoformat()
                decision["side"] = side
                decision["quantity"] = quantity
                decision["fill_price"] = float(fill_price)
                decision["conversion_rate_to_inr"] = float(fx_rate)
                decision["fees_inr"] = float(fee)
                decision["slippage_inr"] = float(slippage)
                decision["realized_pnl_inr"] = float(realized.quantize(CENT))
                trade_row = {
                    "timestamp": stamp.isoformat(),
                    "market_type": market_type,
                    "symbol": candle.symbol.upper(),
                    "side": side,
                    "quantity": quantity,
                    "quantity_unit": base_currency if market_type == "FOREX" else "shares",
                    "news_title": item["article"]["title"],
                    "fill_price": float(fill_price),
                    "quote_currency": quote_currency,
                    "conversion_rate_to_inr": float(fx_rate),
                    "value_inr": float(gross_inr.quantize(CENT)),
                    "fees_inr": float(fee),
                    "slippage_inr": float(slippage),
                    "realized_pnl_inr": float(realized.quantize(CENT)),
                }
                total_fills += 1
                if len(trades) < 1000:
                    trades.append(trade_row)

        # The candle close becomes known only after any orders filled at its open.
        for candle in bars:
            key = _instrument_key(candle.market_type, candle.symbol)
            latest_prices[key] = (stamp, _latest_price(candle, "close"), candle)
            if candle.market_type == "FOREX":
                pair = (candle.base_currency or "", candle.quote_currency)
                latest_close_rates[pair] = (stamp, _latest_price(candle, "close"))

        _market_value, equity = mark_portfolio(stamp)
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            max_drawdown = max(max_drawdown, (peak_equity - equity) / peak_equity * Decimal(100))
        equity_curve.append({"timestamp": stamp.isoformat(), "equity": float(equity.quantize(CENT))})

        # Events are observed at the first replay timestamp at or after publication.
        while news_index < len(news) and _utc(news[news_index].published_at) <= stamp:
            article_input = news[news_index]
            news_index += 1
            article = {
                "title": article_input.title,
                "description": article_input.description,
                "source": article_input.source,
                "url": article_input.url,
                "published_at": _utc(article_input.published_at).isoformat(),
                "category": "historical",
            }
            signal = evaluate_articles([article], config, now=stamp)[0]
            if signal["article_id"] in seen_articles:
                continue
            seen_articles.add(signal["article_id"])
            if signal["action"] not in {"BUY", "SELL"}:
                decisions.append({
                    "article_id": signal["article_id"],
                    "title": article_input.title,
                    "published_at": article["published_at"],
                    "observed_at": stamp.isoformat(),
                    "symbols": signal["symbols"],
                    "action": signal["action"],
                    "confidence": signal["confidence"],
                    "status": "rejected",
                    "reason": signal["decision_reason"],
                })
                continue
            for symbol in signal["symbols"]:
                instrument = _instrument_key(signal["market_type"], symbol)
                decision = {
                    "article_id": signal["article_id"],
                    "title": article_input.title,
                    "published_at": article["published_at"],
                    "observed_at": stamp.isoformat(),
                    "symbol": instrument[1],
                    "action": signal["action"],
                    "confidence": signal["confidence"],
                    "status": "queued",
                    "reason": "Accepted after publication; waiting for a later matching candle open.",
                }
                decisions.append(decision)
                if instrument not in bars_by_instrument:
                    decision["status"] = "rejected"
                    decision["reason"] = "No matching historical instrument bars were provided."
                else:
                    pending[instrument].append({
                        "queued_at": stamp,
                        "article": article,
                        "decision": decision,
                    })

    for items in pending.values():
        for item in items:
            item["decision"]["status"] = "unfilled"
            item["decision"]["reason"] = "The dataset ended before a later matching candle open was available."

    # Keep chart output bounded while calculating drawdown over every replay timestamp.
    max_curve_points = 1200
    if len(equity_curve) > max_curve_points:
        step = (len(equity_curve) - 1) / (max_curve_points - 1)
        sampled = [equity_curve[round(index * step)] for index in range(max_curve_points - 1)]
        sampled.append(equity_curve[-1])
        equity_curve = sampled

    for article_input in news[news_index:]:
        decisions.append({
            "title": article_input.title,
            "published_at": _utc(article_input.published_at).isoformat(),
            "action": "UNPROCESSED",
            "status": "unfilled",
            "reason": "The news was published after the supplied candle history ended.",
        })

    ending_equity = _decimal(equity_curve[-1]["equity"])
    return_percent = (ending_equity / _decimal(request.starting_cash) - 1) * 100
    status_counts = defaultdict(int)
    for decision in decisions:
        status_counts[decision["status"]] += 1
    decision_limit = 2000
    return {
        "mode": "historical_replay_simulation",
        "dataset_name": request.dataset_name,
        "data_rights_attested": True,
        "strategy_version": strategy_version,
        "strategy_config": config,
        "start_timestamp": timeline[0].isoformat(),
        "end_timestamp": timeline[-1].isoformat(),
        "starting_cash_inr": float(_decimal(request.starting_cash).quantize(CENT)),
        "ending_equity_inr": float(ending_equity.quantize(CENT)),
        "return_percent": float(return_percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "max_drawdown_percent": float(max_drawdown.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "cash_inr": float(cash.quantize(CENT)),
        "realized_pnl_inr": float(realized_total.quantize(CENT)),
        "fees_inr": float(fees_total.quantize(CENT)),
        "slippage_inr": float(slippage_total.quantize(CENT)),
        "bar_count": len(request.candles),
        "signal_count": len(decisions),
        "filled_trade_count": total_fills,
        "rejected_signal_count": status_counts["rejected"],
        "unfilled_signal_count": status_counts["unfilled"],
        "equity_curve": equity_curve,
        "trades": trades,
        "trades_truncated": total_fills > len(trades),
        "decisions": decisions[:decision_limit],
        "decisions_truncated": len(decisions) > decision_limit,
        "notice": (
            "Results replay only the user-supplied dataset and are not independently verified. "
            "Fills occur at the next matching candle open with virtual costs; no broker or live data service is used."
        ),
    }
