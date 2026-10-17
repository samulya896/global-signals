"""Historical replay tests use only explicit local fixture data."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.backtest import replay_backtest
from backend.schemas import HistoricalBacktestRequest


START = datetime(2025, 1, 6, 9, 15, tzinfo=timezone.utc)


def candle(stamp, *, symbol="NIFTYBEES", market_type="EQUITY", open_=100, high=110, low=90, close=100,
           base_currency=None, quote_currency="INR"):
    return {
        "market_type": market_type,
        "symbol": symbol,
        "timestamp": stamp.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "base_currency": base_currency,
        "quote_currency": quote_currency,
    }


def request(candles, news, starting_cash=100_000):
    return HistoricalBacktestRequest.model_validate({
        "dataset_name": "fixture-only",
        "data_rights_confirmed": True,
        "starting_cash": starting_cash,
        "candles": candles,
        "news": news,
    })


def test_news_fills_only_at_the_next_matching_candle_open():
    bars = [
        candle(START, open_=100, high=105, low=98, close=102),
        candle(START + timedelta(days=1), open_=110, high=125, low=108, close=120),
        candle(START + timedelta(days=2), open_=118, high=132, low=116, close=130),
    ]
    articles = [{
        "title": "Nifty rallies on strong growth",
        "published_at": START.isoformat(),
        "url": "https://fixture.example/nifty-rallies",
    }]

    result = replay_backtest(request(bars, articles), {"cooldown_minutes": 0}, strategy_version=4)

    assert result["mode"] == "historical_replay_simulation"
    assert result["strategy_version"] == 4
    assert result["filled_trade_count"] == 1
    trade = result["trades"][0]
    assert trade["timestamp"] == (START + timedelta(days=1)).isoformat()
    assert trade["fill_price"] > 110
    assert result["fees_inr"] > 0
    assert result["slippage_inr"] > 0
    assert result["ending_equity_inr"] > result["starting_cash_inr"]
    assert result["equity_curve"][0]["equity"] == result["starting_cash_inr"]
    assert result["trades"][0]["side"] == "buy"


def test_news_on_last_bar_is_not_filled_using_that_bar():
    bars = [candle(START), candle(START + timedelta(days=1))]
    articles = [{
        "title": "Nifty rallies",
        "published_at": (START + timedelta(days=1)).isoformat(),
        "url": "https://fixture.example/last-bar-news",
    }]

    result = replay_backtest(request(bars, articles), {"cooldown_minutes": 0})

    assert result["filled_trade_count"] == 0
    assert result["unfilled_signal_count"] == 1
    assert "dataset ended" in result["decisions"][0]["reason"].lower()


def test_forex_trade_is_rejected_without_a_fresh_quote_currency_conversion():
    bars = [
        candle(START, symbol="EUR/USD", market_type="FOREX", open_=1.02, high=1.04, low=1.01, close=1.03,
               base_currency="EUR", quote_currency="USD"),
        candle(START + timedelta(days=1), symbol="EUR/USD", market_type="FOREX", open_=1.03, high=1.05, low=1.02, close=1.04,
               base_currency="EUR", quote_currency="USD"),
    ]
    articles = [{
        "title": "EUR/USD rallies after strong growth",
        "published_at": START.isoformat(),
        "url": "https://fixture.example/fx-rallies",
    }]

    result = replay_backtest(request(bars, articles), {"cooldown_minutes": 0})

    assert result["filled_trade_count"] == 0
    assert result["rejected_signal_count"] == 1
    assert "USD/INR" in result["decisions"][0]["reason"]
    assert result["cash_inr"] == result["starting_cash_inr"]


def test_forex_trade_uses_supplied_inr_conversion_bars():
    bars = [
        candle(START, symbol="EUR/USD", market_type="FOREX", open_=1.02, high=1.04, low=1.01, close=1.03,
               base_currency="EUR", quote_currency="USD"),
        candle(START, symbol="USD/INR", market_type="FOREX", open_=85, high=86, low=84, close=85.5,
               base_currency="USD", quote_currency="INR"),
        candle(START + timedelta(days=1), symbol="EUR/USD", market_type="FOREX", open_=1.03, high=1.05, low=1.02, close=1.04,
               base_currency="EUR", quote_currency="USD"),
        candle(START + timedelta(days=1), symbol="USD/INR", market_type="FOREX", open_=85.5, high=86, low=85, close=85.8,
               base_currency="USD", quote_currency="INR"),
    ]
    articles = [{
        "title": "EUR/USD rallies after strong growth",
        "published_at": START.isoformat(),
        "url": "https://fixture.example/fx-rallies-with-conversion",
    }]

    result = replay_backtest(request(bars, articles), {"cooldown_minutes": 0})

    assert result["filled_trade_count"] == 1
    assert result["trades"][0]["conversion_rate_to_inr"] == 85.5
    assert result["trades"][0]["quantity_unit"] == "EUR"


def test_virtual_sell_closes_only_held_units_and_records_realized_pnl():
    bars = [
        candle(START, open_=100, high=105, low=98, close=102),
        candle(START + timedelta(hours=1), open_=100, high=125, low=99, close=120),
        candle(START + timedelta(hours=2), open_=120, high=125, low=110, close=115),
        candle(START + timedelta(hours=3), open_=115, high=120, low=110, close=112),
    ]
    articles = [
        {"title": "Nifty rallies", "published_at": START.isoformat(), "url": "https://fixture.example/buy"},
        {"title": "Nifty falls", "published_at": (START + timedelta(hours=1)).isoformat(), "url": "https://fixture.example/sell"},
    ]

    result = replay_backtest(request(bars, articles), {"cooldown_minutes": 0})

    assert [trade["side"] for trade in result["trades"]] == ["buy", "sell"]
    assert result["trades"][1]["timestamp"] == (START + timedelta(hours=2)).isoformat()
    assert result["trades"][1]["realized_pnl_inr"] > 0
    assert result["cash_inr"] > result["starting_cash_inr"]
    assert result["ending_equity_inr"] == result["cash_inr"]


def test_daily_loss_control_blocks_new_buy_after_realized_loss():
    bars = [
        candle(START, open_=100, high=102, low=99, close=100),
        candle(START + timedelta(minutes=1), open_=100, high=102, low=99, close=100),
        candle(START + timedelta(minutes=2), open_=50, high=55, low=45, close=50),
        candle(START + timedelta(minutes=3), open_=50, high=55, low=45, close=50),
    ]
    articles = [
        {"title": "Nifty rallies", "published_at": START.isoformat(), "url": "https://fixture.example/risk-buy"},
        {"title": "Nifty falls", "published_at": (START + timedelta(minutes=1)).isoformat(), "url": "https://fixture.example/risk-sell"},
        {"title": "Nifty rallies", "published_at": (START + timedelta(minutes=2)).isoformat(), "url": "https://fixture.example/risk-buy-again"},
    ]

    result = replay_backtest(
        request(bars, articles),
        {"cooldown_minutes": 0, "daily_loss_limit_percent": 0.1},
    )

    assert result["filled_trade_count"] == 2
    assert result["trades"][1]["realized_pnl_inr"] < 0
    risk_rejection = next(item for item in result["decisions"] if item["status"] == "rejected")
    assert "daily realized-loss limit" in risk_rejection["reason"]


def test_dataset_rejects_missing_rights_confirmation_duplicate_bars_and_naive_times():
    with pytest.raises(ValidationError):
        HistoricalBacktestRequest.model_validate({
            "dataset_name": "unattested",
            "data_rights_confirmed": False,
            "starting_cash": 100_000,
            "candles": [candle(START), candle(START + timedelta(days=1))],
            "news": [{"title": "Nifty rises", "published_at": START.isoformat()}],
        })
    with pytest.raises(ValidationError):
        request([candle(START), candle(START), candle(START + timedelta(days=1))], [
            {"title": "Nifty rises", "published_at": START.isoformat()},
        ])
    with pytest.raises(ValidationError):
        request([candle(START.replace(tzinfo=None)), candle(START + timedelta(days=1))], [
            {"title": "Nifty rises", "published_at": START.isoformat()},
        ])
