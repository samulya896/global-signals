"""Explainable news rules with explicit instrument mentions and cautious sentiment."""

from datetime import datetime, timezone
import hashlib
import re


# A category is not enough to select an asset. Signals are attached only when the
# article text names one of these supported tickers, indices, companies, or pairs.
EQUITY_ALIASES = {
    "NIFTYBEES": ("niftybees", "nifty 50", "nifty index", "nifty"),
    "BANKBEES": ("bankbees", "bank nifty", "nifty bank"),
    "ITBEES": ("itbees", "nifty it", "nifty information technology"),
    "GOLDBEES": ("goldbees", "gold etf"),
    "SILVERBEES": ("silverbees", "silver etf"),
    "NSE:RELIANCE": ("reliance industries", "reliance"),
    "NSE:TCS": ("tata consultancy services", "tcs"),
    "NSE:INFY": ("infosys",),
    "NSE:HDFCBANK": ("hdfc bank",),
    "NSE:ICICIBANK": ("icici bank",),
    "NSE:SBIN": ("state bank of india", "sbi"),
    "NSE:ITC": ("itc limited", "itc"),
    "NSE:LT": ("larsen and toubro", "l&t"),
}

FOREX_ALIASES = {
    "EUR/USD": ("eur/usd", "eurusd", "eur-usd", "euro dollar", "euro vs dollar"),
    "GBP/USD": ("gbp/usd", "gbpusd", "gbp-usd", "sterling dollar", "pound vs dollar"),
    "USD/JPY": ("usd/jpy", "usdjpy", "usd-jpy", "dollar yen", "dollar vs yen"),
    "USD/INR": ("usd/inr", "usdinr", "usd-inr", "dollar rupee", "dollar vs rupee"),
    "AUD/USD": ("aud/usd", "audusd", "aud-usd", "australian dollar vs us dollar"),
    "USD/CAD": ("usd/cad", "usdcad", "usd-cad", "us dollar vs canadian dollar"),
    "USD/CHF": ("usd/chf", "usdchf", "usd-chf", "dollar franc"),
    "NZD/USD": ("nzd/usd", "nzdusd", "nzd-usd", "new zealand dollar vs us dollar"),
    "EUR/GBP": ("eur/gbp", "eurgbp", "eur-gbp", "euro pound"),
    "EUR/JPY": ("eur/jpy", "eurjpy", "eur-jpy", "euro yen"),
    "GBP/JPY": ("gbp/jpy", "gbpjpy", "gbp-jpy", "pound yen"),
}

POSITIVE_TERMS = (
    "beats estimates", "beat estimates", "record profit", "strong growth", "raises guidance",
    "upgrade", "upgraded", "outperforms", "outperformed", "surge", "surges", "surged",
    "rally", "rallies", "rallied", "rise", "rises", "rose", "gain", "gains", "gained",
    "strengthens", "strengthened", "bullish", "expands", "expansion",
)
NEGATIVE_TERMS = (
    "misses estimates", "missed estimates", "downgrade", "downgraded", "cuts guidance",
    "weak growth", "loss", "losses", "layoffs", "underperforms", "underperformed", "selloff",
    "crash", "falls", "fall", "fell", "drops", "drop", "decline", "declines", "declined",
    "weakens", "weakened", "bearish", "contraction",
)


def _mentioned(text: str, alias: str) -> bool:
    escaped = re.escape(alias.lower()).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


def _mentioned_symbols(text: str, aliases: dict[str, tuple[str, ...]]) -> list[str]:
    return [symbol for symbol, names in aliases.items() if any(_mentioned(text, name) for name in names)]


def classify_article(article):
    """Return a transparent, non-predictive rule signal for one provider article."""
    title = str(article.get("title") or "")
    text = f"{title} {article.get('description') or ''}".lower()
    category = str(article.get("category") or "general").lower()

    forex_symbols = _mentioned_symbols(text, FOREX_ALIASES)
    if forex_symbols:
        symbols = forex_symbols
        market_type = "FOREX"
    else:
        symbols = _mentioned_symbols(text, EQUITY_ALIASES)
        market_type = "EQUITY"

    positive = [term for term in POSITIVE_TERMS if _mentioned(text, term)]
    negative = [term for term in NEGATIVE_TERMS if _mentioned(text, term)]
    score = len(positive) - len(negative)
    if not symbols:
        action = "HOLD"
        sentiment = "uncertain" if positive and negative else "neutral"
        confidence = 0.4
        explanation = "No exact supported instrument mention was found; no asset was selected for this article."
    elif positive and negative:
        action = "HOLD"
        sentiment = "uncertain"
        confidence = 0.45
        explanation = f"Conflicting terms matched: positive {', '.join(positive)}; negative {', '.join(negative)}."
    elif score > 0:
        action = "BUY"
        sentiment = "positive"
        confidence = min(0.9, 0.65 + 0.1 * (len(positive) - 1))
        explanation = f"Explicit instrument mention; positive terms matched: {', '.join(positive)}."
    elif score < 0:
        action = "SELL"
        sentiment = "negative"
        confidence = min(0.9, 0.65 + 0.1 * (len(negative) - 1))
        explanation = f"Explicit instrument mention; negative terms matched: {', '.join(negative)}."
    else:
        action = "HOLD"
        sentiment = "neutral"
        confidence = 0.5
        explanation = "An instrument was mentioned, but no configured directional terms matched; the rule returned HOLD."

    url = article.get("url")
    article_id = hashlib.sha256(str(url or title).encode("utf-8")).hexdigest()
    return {
        "article_id": article_id,
        "title": title,
        "source": article.get("source"),
        "url": url,
        "category": category,
        "market_type": market_type,
        "symbols": symbols,
        "action": action,
        "sentiment": sentiment,
        "score": score,
        "confidence": round(confidence, 2),
        "matched_keywords": positive + negative,
        "explanation": explanation,
        "strategy_version": "explicit-mention-rules-v2",
        "decision_at": datetime.now(timezone.utc).isoformat(),
        "published_at": article.get("published_at"),
        "retrieved_at": article.get("retrieved_at"),
        "source_reliability": "unrated",
    }


def build_signals(articles):
    signals = []
    seen = set()
    for article in articles:
        signal = classify_article(article)
        if signal["article_id"] not in seen:
            seen.add(signal["article_id"])
            signals.append(signal)
    return signals
