from datetime import datetime, timedelta, timezone

import pytest

from backend.config import load_settings
from backend.news import canonicalize_url
from backend.signals import classify_article
from backend.strategy_engine import DEFAULT_STRATEGY_CONFIG, evaluate_articles


@pytest.mark.parametrize(
    "override",
    [
        {"APP_ENV": "produciton"},
        {"APP_ENV": "production", "FRONTEND_ORIGINS": ""},
        {"APP_ENV": "production", "FRONTEND_ORIGINS": "https://app.example/path"},
        {"APP_ENV": "production", "FRONTEND_ORIGINS": "https://app.example,https://other.example?q=1"},
        {"SIM_FEE_BPS": "-1"},
        {"SIM_SLIPPAGE_BPS": "NaN"},
        {"SIM_MAX_EXPOSURE_PERCENT": "101"},
        {"SIM_STARTING_CASH": "0"},
        {"SESSION_HOURS": "0"},
    ],
)
def test_invalid_environment_is_rejected(override):
    with pytest.raises(RuntimeError):
        load_settings({"APP_ENV": "development", **override})


def test_valid_production_settings_require_secure_exact_origin():
    settings = load_settings({
        "APP_ENV": "production",
        "FRONTEND_ORIGINS": "https://app.example.com",
        "SIM_MAX_EXPOSURE_PERCENT": "90",
    })
    assert settings.app_env == "production"
    assert settings.frontend_origins == ("https://app.example.com",)
    assert settings.max_exposure_percent == 90


def test_news_url_canonicalization_blocks_unsafe_schemes_and_tracking_ids():
    canonical = canonicalize_url("HTTPS://Example.COM/article?utm_source=test&id=4#top")
    assert canonical == "https://example.com/article?id=4"
    assert canonicalize_url("javascript:alert(1)") is None
    assert canonicalize_url("https://user:password@example.com/story") is None


def test_strategy_preview_filters_old_low_confidence_and_invalid_dates():
    now = datetime.now(timezone.utc)
    articles = [
        {
            "title": "Nifty rally and strong growth",
            "category": "markets",
            "published_at": now.isoformat(),
            "url": "https://news.example/current",
        },
        {
            "title": "Neutral markets report",
            "category": "markets",
            "published_at": now.isoformat(),
            "url": "https://news.example/neutral",
        },
        {
            "title": "Banks rise",
            "category": "markets",
            "published_at": (now - timedelta(days=3)).isoformat(),
            "url": "https://news.example/old",
        },
        {
            "title": "Oil rises",
            "category": "energy",
            "published_at": None,
            "url": "https://news.example/no-date",
        },
    ]
    config = {**DEFAULT_STRATEGY_CONFIG, "max_event_age_hours": 24, "min_confidence": 0.65}
    result = evaluate_articles(articles, config, now=now)

    assert result[0]["action"] == "BUY" and result[0]["accepted"] is True
    assert result[1]["action"] == "HOLD" and "confidence" in result[1]["decision_reason"]
    assert result[2]["action"] == "HOLD" and "older" in result[2]["decision_reason"]
    assert result[3]["action"] == "HOLD" and "timestamp" in result[3]["decision_reason"]
    assert all("orders_generated" not in row for row in result)


def test_news_signal_requires_instrument_mention_and_handles_explicit_fx_pairs():
    unrelated = classify_article({"title": "The euro rises after central bank comments"})
    assert unrelated["action"] == "HOLD" and unrelated["symbols"] == []

    fx_pair = classify_article({"title": "EUR/USD rises after central bank comments"})
    assert fx_pair["market_type"] == "FOREX"
    assert fx_pair["symbols"] == ["EUR/USD"] and fx_pair["action"] == "BUY"

    conflicting = classify_article({"title": "Nifty rises then falls in volatile session"})
    assert conflicting["symbols"] == ["NIFTYBEES"]
    assert conflicting["action"] == "HOLD" and conflicting["sentiment"] == "uncertain"
