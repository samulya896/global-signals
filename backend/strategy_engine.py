"""Explainable, read-only strategy evaluation for provider-sourced news."""

from datetime import datetime, timedelta, timezone
from typing import Any

from .signals import classify_article


DEFAULT_STRATEGY_CONFIG: dict[str, int | float] = {
    "enabled": False,
    "min_confidence": 0.65,
    "max_event_age_hours": 24,
    "max_position_percent": 5,
    "max_portfolio_exposure_percent": 50,
    "cooldown_minutes": 60,
    "daily_loss_limit_percent": 5,
}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def evaluate_articles(
    articles: list[dict[str, Any]],
    config: dict[str, int | float],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Classify articles and explain why a rule accepts or rejects each signal.

    This function only produces analysis. It never creates orders or changes a portfolio.
    """
    decision_time = now or datetime.now(timezone.utc)
    if decision_time.tzinfo is None:
        decision_time = decision_time.replace(tzinfo=timezone.utc)
    decision_time = decision_time.astimezone(timezone.utc)
    oldest_allowed = decision_time - timedelta(hours=float(config["max_event_age_hours"]))
    results: list[dict[str, Any]] = []
    seen_articles: set[str] = set()

    for article in articles:
        signal = classify_article(article)
        if signal["article_id"] in seen_articles:
            continue
        seen_articles.add(signal["article_id"])

        published = _parse_timestamp(signal.get("published_at"))
        if published is None:
            reason = "Publication timestamp is missing or invalid; freshness cannot be verified."
            action = "HOLD"
        elif published > decision_time:
            reason = "Publication timestamp is in the future; the event was rejected."
            action = "HOLD"
        elif published < oldest_allowed:
            reason = "Event is older than the configured maximum age."
            action = "HOLD"
        elif signal["confidence"] < float(config["min_confidence"]):
            reason = "Signal confidence is below the configured threshold."
            action = "HOLD"
        else:
            reason = signal["explanation"]
            action = signal["action"]

        results.append({
            **signal,
            "action": action,
            "accepted": action != "HOLD",
            "decision_reason": reason,
            "age_minutes": round((decision_time - published).total_seconds() / 60, 1) if published else None,
        })

    return results
