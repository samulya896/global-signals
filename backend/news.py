
import os
from pathlib import Path
from datetime import datetime, timezone
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("NEWS_API_KEY")
NEWS_URL = "https://newsapi.org/v2/everything"


_CACHE_TTL_SECONDS = 60
_live_cache: tuple[float, tuple[tuple[str, int], list[dict]]] | None = None
_cache_lock = threading.Lock()


def get_news():
    """No fabricated headlines are shown when an authorized provider is unavailable."""
    return []


def get_news_by_category(category):
    return []


def news_provider_status():
    production_allowed = os.getenv("NEWSAPI_PRODUCTION_AUTHORIZED", "false").lower() == "true"
    return {
        "provider": "NewsAPI",
        "configured": bool(API_KEY),
        "production_authorized": production_allowed,
        "sample_news_enabled": False,
        "message": "Configure NEWS_API_KEY on the backend to load attributed provider articles." if not API_KEY else "NewsAPI's Developer plan is restricted to development and testing; production requires an authorized plan.",
    }


def _normalize_timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def canonicalize_url(value):
    """Return a normalized HTTP(S) article URL, rejecting unsafe or malformed schemes."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlsplit(value.strip())
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not hostname or parsed.username or parsed.password:
        return None
    host = hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = (parsed.scheme.lower() == "https" and port == 443) or (parsed.scheme.lower() == "http" and port == 80)
    netloc = host if port is None or default_port else f"{host}:{port}"
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", urlencode(query, doseq=True), ""))


def get_live_news(query="oil OR geopolitics", page_size=10):
    global _live_cache
    if not API_KEY:
        raise RuntimeError(
            "NEWS_API_KEY is missing. Configure an authorized NewsAPI plan on the backend."
        )
    if os.getenv("APP_ENV", "development").lower() == "production" and os.getenv(
        "NEWSAPI_PRODUCTION_AUTHORIZED", "false"
    ).lower() != "true":
        raise RuntimeError("NewsAPI production usage is not authorized in configuration; no provider request was made.")

    page_size = max(1, min(int(page_size), 50))
    cache_key = (query, page_size)
    now = time.monotonic()
    with _cache_lock:
        if _live_cache and _live_cache[0] > now and _live_cache[1][0] == cache_key:
            return _live_cache[1][1]

    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": page_size,
    }

    response = None
    for attempt in range(3):
        try:
            response = requests.get(
                NEWS_URL,
                params=params,
                headers={"X-Api-Key": API_KEY},
                timeout=10,
            )
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(0.25 * (2 ** attempt))
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == 2:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After", "")
            try:
                pause = min(max(int(retry_after), 0), 3)
            except ValueError:
                pause = 0.25 * (2 ** attempt)
            time.sleep(pause)
            continue
        response.raise_for_status()
        break

    if response is None:
        return []

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("The news provider response must be a JSON object.")
    if data.get("status") not in (None, "ok"):
        raise ValueError("NewsAPI reported an unsuccessful response.")

    provider_articles = data.get("articles", [])
    if not isinstance(provider_articles, list):
        raise ValueError("The news provider articles field must be a list.")

    articles = []
    seen_articles = set()
    retrieved_at = datetime.now(timezone.utc).isoformat()

    for item in provider_articles:
        if not isinstance(item, dict):
            raise ValueError("Each news provider article must be a JSON object.")
        source = item.get("source")
        if source is not None and not isinstance(source, dict):
            raise ValueError("The news provider article source must be a JSON object.")

        canonical_url = canonicalize_url(item.get("url"))
        title = item.get("title")
        source_name = (source or {}).get("name")
        dedupe_key = canonical_url or f"{str(source_name or '').casefold()}:{str(title or '').casefold().strip()}"
        if dedupe_key in seen_articles:
            continue
        seen_articles.add(dedupe_key)

        articles.append({
            "title": title,
            "source": source_name,
            "published_at": _normalize_timestamp(item.get("publishedAt")),
            "retrieved_at": retrieved_at,
            "provider": "NewsAPI",
            "category": "unclassified",
            "url": canonical_url,
            "description": item.get("description"),
        })

    with _cache_lock:
        _live_cache = (time.monotonic() + _CACHE_TTL_SECONDS, (cache_key, articles))
    return articles
