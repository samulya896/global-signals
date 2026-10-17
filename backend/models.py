"""Normalized user, paper portfolio, order, and audit records."""

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    sessions: Mapped[list["SessionRecord"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    portfolio: Mapped["VirtualPortfolio"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    strategy_versions: Mapped[list["StrategyVersion"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    strategy_executions: Mapped[list["StrategyExecution"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    watchlist_items: Mapped[list["WatchlistItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship(back_populates="sessions")


class VirtualPortfolio(Base):
    __tablename__ = "virtual_portfolios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    starting_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    user: Mapped[User] = relationship(back_populates="portfolio")
    positions: Mapped[list["VirtualPosition"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")
    orders: Mapped[list["SimulatedOrder"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")


class VirtualPosition(Base):
    __tablename__ = "virtual_positions"
    __table_args__ = (UniqueConstraint("portfolio_id", "symbol", name="uq_position_portfolio_symbol"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("virtual_portfolios.id", ondelete="CASCADE"), index=True, nullable=False)
    market_type: Mapped[str] = mapped_column(String(8), default="EQUITY", server_default="EQUITY", nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    base_currency: Mapped[str | None] = mapped_column(String(3))
    quote_currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR", nullable=False)
    average_entry: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    average_entry_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    portfolio: Mapped[VirtualPortfolio] = relationship(back_populates="positions")


class SimulatedOrder(Base):
    __tablename__ = "simulated_orders"
    __table_args__ = (UniqueConstraint("portfolio_id", "idempotency_key", name="uq_order_portfolio_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("virtual_portfolios.id", ondelete="CASCADE"), index=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    market_type: Mapped[str] = mapped_column(String(8), default="EQUITY", server_default="EQUITY", nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    base_currency: Mapped[str | None] = mapped_column(String(3))
    quote_currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR", nullable=False)
    quote_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    fill_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    ask: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    conversion_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=1, server_default="1", nullable=False)
    value_inr: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, server_default="0", nullable=False)
    source_provider: Mapped[str] = mapped_column(String(80), default="synthetic-demo", server_default="synthetic-demo", nullable=False)
    price_basis: Mapped[str] = mapped_column(String(40), default="synthetic demo value", server_default="synthetic demo value", nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    slippage: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="filled", nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="simulation", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    portfolio: Mapped[VirtualPortfolio] = relationship(back_populates="orders")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("virtual_portfolios.id", ondelete="CASCADE"), index=True, nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class StrategyVersion(Base):
    """Immutable, user-scoped snapshots of the news strategy's rule settings."""

    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("user_id", "version", name="uq_strategy_user_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    user: Mapped[User] = relationship(back_populates="strategy_versions")


class StrategyExecution(Base):
    """Idempotency record for worker decisions; these can reference paper orders only."""

    __tablename__ = "strategy_executions"
    __table_args__ = (UniqueConstraint("user_id", "article_id", name="uq_strategy_user_article"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    article_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    simulated_order_id: Mapped[str | None] = mapped_column(ForeignKey("simulated_orders.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    user: Mapped[User] = relationship(back_populates="strategy_executions")


class WatchlistItem(Base):
    """Per-user canonical market instruments; no provider token is stored here."""

    __tablename__ = "market_watchlist"
    __table_args__ = (UniqueConstraint("user_id", "market_type", "symbol", name="uq_watchlist_user_market_symbol"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    market_type: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_currency: Mapped[str | None] = mapped_column(String(3))
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    user: Mapped[User] = relationship(back_populates="watchlist_items")
