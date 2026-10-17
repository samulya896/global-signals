
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi import Depends, Header, Request
from requests.exceptions import HTTPError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from requests.exceptions import RequestException
from starlette.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .news import get_news, get_news_by_category, get_live_news, news_provider_status
from .config import SETTINGS, production_paper_trading_enabled, simulator_kill_switch_active
from .signals import build_signals
from .auth_api import router as auth_router
from .database import get_db
from .models import SessionRecord, StrategyVersion, User, WatchlistItem
from .paper import execute_simulated_order, performance, portfolio_history, portfolio_snapshot, reset_portfolio
from .market_data import MarketDataError, MarketType, get_market_data_provider, market_data_status
from .schemas import HistoricalBacktestRequest, ResetPortfolioRequest, StrategyConfigRequest, TradeRequest, WatchlistRequest
from .security import get_session, require_csrf
from .simulator import SYMBOLS
from .rate_limit import enforce_rate_limit
from .strategy_engine import DEFAULT_STRATEGY_CONFIG, evaluate_articles
from .backtest import replay_backtest


app = FastAPI(title="Global Signals API")
STATIC_DIR = Path(__file__).resolve().parent / "static"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")
app.include_router(auth_router)

app_env = SETTINGS.app_env
allowed_origins = list(SETTINGS.frontend_origins)
class SecurityHeadersMiddleware:
    """Pure ASGI middleware avoids the buffering behavior of BaseHTTPMiddleware."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                ])
                if os.getenv("APP_ENV", "development").lower() == "production":
                    headers.append((b"strict-transport-security", b"max-age=63072000; includeSubDomains"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key", "X-CSRF-Token"],
)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    session_record, user = get_session(db, request)
    request.state.session_record = session_record
    return user


def _strategy_config_payload(record: StrategyVersion | None) -> dict:
    if record is None:
        return {"version": 0, "config": DEFAULT_STRATEGY_CONFIG, "updated_at": None}
    return {"version": record.version, "config": record.config, "updated_at": record.created_at.isoformat()}


@app.get("/")
def home():
    built_index = FRONTEND_DIST / "index.html"
    if built_index.is_file():
        return FileResponse(built_index)
    return JSONResponse({
        "service": "Global Signals API",
        "status": "api-only",
        "message": "The React frontend is served separately. See the API docs at /docs.",
    })


@app.get("/api/v1/health")
@app.get("/api/health")
def health():
    return {"status": "healthy"}


@app.get("/api/v1/ready")
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "healthy"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is not ready.") from exc


@app.get("/api/v1/news")
@app.get("/api/news")
def read_news():
    return get_news()


@app.get("/api/v1/news/status")
def read_news_status():
    return news_provider_status()


@app.get("/api/v1/news/live")
@app.get("/api/news/live")
def read_live_news(request: Request):
    try:
        enforce_rate_limit(request, "manual_news_refresh", 5, 60)
        return get_live_news()

    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            raise HTTPException(status_code=503, detail="News provider rate limit reached; try again later.") from exc
        raise HTTPException(status_code=502, detail="The external news provider returned an error.") from exc

    except RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail="The external news provider could not be reached.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="The news provider returned invalid JSON.",
        ) from exc


@app.get("/api/v1/signals")
@app.get("/api/signals")
def read_signals():
    if not news_provider_status()["configured"]:
        return []
    if os.getenv("APP_ENV", "development").lower() == "production" and not news_provider_status()["production_authorized"]:
        return []
    try:
        return build_signals(get_live_news(query="India NSE Nifty OR Sensex OR RBI", page_size=10))
    except (RequestException, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="News signals are temporarily unavailable.") from exc


@app.get("/api/v1/market")
@app.get("/api/market")
def read_market(user: User = Depends(current_user)):
    del user
    provider = get_market_data_provider(MarketType.EQUITY)
    try:
        return [provider.get_quote(symbol).model_dump(mode="json") for symbol in SYMBOLS]
    except MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get("/api/v1/markets/status")
def read_market_data_status(user: User = Depends(current_user)):
    del user
    return market_data_status()


@app.get("/api/v1/markets/instruments")
def search_market_instruments(
    market_type: MarketType = MarketType.EQUITY,
    q: str = Query(min_length=1, max_length=50),
    limit: int = Query(default=20, ge=1, le=30),
    user: User = Depends(current_user),
):
    del user
    provider = get_market_data_provider(market_type, allow_demo=True)
    try:
        return [item.model_dump(mode="json") for item in provider.search_instruments(q, limit)]
    except MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get("/api/v1/markets/quote")
def read_market_quote(
    market_type: MarketType = MarketType.EQUITY,
    symbol: str = Query(min_length=1, max_length=32),
    user: User = Depends(current_user),
):
    del user
    provider = get_market_data_provider(market_type, allow_demo=True)
    try:
        return provider.get_quote(symbol).model_dump(mode="json")
    except MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get("/api/v1/markets/candles")
def read_market_candles(
    market_type: MarketType = MarketType.EQUITY,
    symbol: str = Query(min_length=1, max_length=32),
    interval: str = Query(default="1day", max_length=8),
    days: int = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=300, ge=1, le=1000),
    user: User = Depends(current_user),
):
    del user
    provider = get_market_data_provider(market_type, allow_demo=False)
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    try:
        candles = provider.get_candles(symbol, interval, start_date, end_date, limit)
        return [item.model_dump(mode="json") for item in candles]
    except MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get("/api/v1/watchlist")
def read_watchlist(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user.id)
        .order_by(WatchlistItem.market_type, WatchlistItem.symbol)
    ).all()
    return [
        {
            "market_type": row.market_type,
            "symbol": row.symbol,
            "name": row.name,
            "base_currency": row.base_currency,
            "quote_currency": row.quote_currency,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@app.post("/api/v1/watchlist", status_code=201)
def add_watchlist_item(
    payload: WatchlistRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_csrf(request, request.state.session_record)
    market = MarketType(payload.market_type)
    provider = get_market_data_provider(market, allow_demo=True)
    search_symbol = payload.symbol.strip().upper()
    if market is MarketType.EQUITY and ":" in search_symbol:
        search_symbol = search_symbol.split(":", 1)[1]
    try:
        instruments = provider.search_instruments(search_symbol, 30)
    except MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    selected = next((item for item in instruments if item.symbol == payload.symbol.strip().upper()), None)
    if selected is None:
        raise HTTPException(status_code=422, detail="Choose a supported provider-listed instrument before saving it.")
    existing = db.scalar(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user.id,
            WatchlistItem.market_type == market.value,
            WatchlistItem.symbol == selected.symbol,
        )
    )
    if existing:
        return {"market_type": existing.market_type, "symbol": existing.symbol, "status": "already_saved"}
    record = WatchlistItem(
        user_id=user.id,
        market_type=market.value,
        symbol=selected.symbol,
        name=selected.name[:120],
        base_currency=selected.base_currency,
        quote_currency=selected.quote_currency,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(WatchlistItem).where(
                WatchlistItem.user_id == user.id,
                WatchlistItem.market_type == market.value,
                WatchlistItem.symbol == selected.symbol,
            )
        )
        if existing is None:
            raise
        return {"market_type": existing.market_type, "symbol": existing.symbol, "status": "already_saved"}
    return {"market_type": record.market_type, "symbol": record.symbol, "status": "saved"}


@app.delete("/api/v1/watchlist")
def remove_watchlist_item(
    request: Request,
    market_type: MarketType,
    symbol: str = Query(min_length=1, max_length=32),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_csrf(request, request.state.session_record)
    record = db.scalar(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user.id,
            WatchlistItem.market_type == market_type.value,
            WatchlistItem.symbol == symbol.strip().upper(),
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Watchlist item was not found for this account.")
    db.delete(record)
    db.commit()
    return {"status": "removed"}


@app.get("/api/v1/portfolio")
@app.get("/api/portfolio")
def read_portfolio(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return portfolio_snapshot(db, user)


@app.get("/api/v1/portfolio/history")
def read_portfolio_history(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return portfolio_history(db, user)


@app.post("/api/v1/portfolio/reset")
def reset_simulated_portfolio(
    payload: ResetPortfolioRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_csrf(request, request.state.session_record)
    return reset_portfolio(db, user)


@app.post("/api/v1/trades")
@app.post("/api/trades")
def create_simulated_trade(
    trade: TradeRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    idempotency_key: str = Header(alias="Idempotency-Key"),
):
    if simulator_kill_switch_active():
        raise HTTPException(status_code=503, detail="The global paper-simulator kill switch is active.")
    if not production_paper_trading_enabled():
        raise HTTPException(status_code=503, detail="Production paper orders are disabled by configuration.")
    session_record: SessionRecord = request.state.session_record
    require_csrf(request, session_record)
    return execute_simulated_order(
        db,
        user,
        trade.symbol,
        trade.side,
        trade.quantity,
        idempotency_key,
        market_type=trade.market_type,
    )


@app.get("/api/v1/performance")
@app.get("/api/performance")
def read_performance(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return performance(db, user)


@app.get("/api/v1/strategy/config")
def read_strategy_config(db: Session = Depends(get_db), user: User = Depends(current_user)):
    record = db.scalar(
        select(StrategyVersion)
        .where(StrategyVersion.user_id == user.id)
        .order_by(StrategyVersion.version.desc())
        .limit(1)
    )
    return _strategy_config_payload(record)


@app.get("/api/v1/strategy/versions")
def read_strategy_versions(db: Session = Depends(get_db), user: User = Depends(current_user)):
    versions = db.scalars(
        select(StrategyVersion)
        .where(StrategyVersion.user_id == user.id)
        .order_by(StrategyVersion.version.desc())
        .limit(20)
    ).all()
    return [_strategy_config_payload(record) for record in versions]


@app.put("/api/v1/strategy/config")
def save_strategy_config(
    payload: StrategyConfigRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_csrf(request, request.state.session_record)
    latest_version = db.scalar(
        select(func.max(StrategyVersion.version)).where(StrategyVersion.user_id == user.id)
    ) or 0
    record = StrategyVersion(
        user_id=user.id,
        version=latest_version + 1,
        config=payload.model_dump(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _strategy_config_payload(record)


@app.post("/api/v1/strategy/preview")
def preview_strategy(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_csrf(request, request.state.session_record)
    record = db.scalar(
        select(StrategyVersion)
        .where(StrategyVersion.user_id == user.id)
        .order_by(StrategyVersion.version.desc())
        .limit(1)
    )
    config = record.config if record else DEFAULT_STRATEGY_CONFIG
    try:
        articles = get_live_news(query="India NSE Nifty OR Sensex OR RBI", page_size=20)
    except (HTTPError, RequestException, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="News is unavailable for strategy preview.") from exc
    signals = evaluate_articles(articles, config)
    return {
        "mode": "read-only strategy preview",
        "strategy_name": "News sentiment rules",
        "strategy_version": f"news-rules-v{record.version if record else 0}",
        "config": config,
        "decision_at": datetime.now(timezone.utc).isoformat(),
        "orders_generated": False,
        "results": signals,
    }


@app.get("/api/v1/backtest")
@app.get("/api/backtest")
def read_backtest(days: int = 90):
    if days < 1 or days > 365:
        raise HTTPException(status_code=400, detail="days must be between 1 and 365.")
    raise HTTPException(
        status_code=503,
        detail=(
            "A genuine backtest is unavailable: configure authorized chronological market candles "
            "and a timestamped historical news-event archive. Synthetic demo prices are not used as backtest data."
        ),
    )


@app.post("/api/v1/backtest/replay")
async def run_historical_backtest(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Replay an attested user dataset in memory; no portfolio rows or providers are touched."""
    require_csrf(request, request.state.session_record)
    enforce_rate_limit(request, "historical_backtest_replay", 5, 60)
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > 5_000_000:
        raise HTTPException(status_code=413, detail="Historical replay JSON must be 5 MB or smaller.")
    raw_body = bytearray()
    async for chunk in request.stream():
        raw_body.extend(chunk)
        if len(raw_body) > 5_000_000:
            raise HTTPException(status_code=413, detail="Historical replay JSON must be 5 MB or smaller.")
    try:
        payload = HistoricalBacktestRequest.model_validate_json(bytes(raw_body))
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors(include_input=False)],
        ) from exc

    if payload.strategy_version == 0:
        record = None
    else:
        version_query = select(StrategyVersion).where(StrategyVersion.user_id == user.id)
        if payload.strategy_version is not None:
            version_query = version_query.where(StrategyVersion.version == payload.strategy_version)
        record = db.scalar(version_query.order_by(StrategyVersion.version.desc()).limit(1))
        if payload.strategy_version is not None and record is None:
            raise HTTPException(status_code=404, detail="That saved strategy version was not found for this account.")
    config = record.config if record else DEFAULT_STRATEGY_CONFIG
    try:
        return replay_backtest(payload, config, strategy_version=record.version if record else 0)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/news/{category}")
@app.get("/api/news/{category}")
def read_news_by_category(category: str):
    return get_news_by_category(category)
