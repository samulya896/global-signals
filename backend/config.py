"""Validated, secret-safe application configuration."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _decimal(env: Mapping[str, str], key: str, default: str, minimum: Decimal, maximum: Decimal) -> Decimal:
    try:
        value = Decimal(env.get(key, default))
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeError(f"{key} must be a valid decimal number.") from exc
    if not value.is_finite() or value < minimum or value > maximum:
        raise RuntimeError(f"{key} must be between {minimum} and {maximum}.")
    return value


def _integer(env: Mapping[str, str], key: str, default: str, minimum: int, maximum: int) -> int:
    try:
        value = int(env.get(key, default))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{key} must be a whole number.") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{key} must be between {minimum} and {maximum}.")
    return value


def _boolean(env: Mapping[str, str], key: str, default: str) -> bool:
    value = env.get(key, default).strip().lower()
    if value not in {"true", "false"}:
        raise RuntimeError(f"{key} must be true or false.")
    return value == "true"


def _origins(env: Mapping[str, str], app_env: str) -> tuple[str, ...]:
    raw = env.get("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    values = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
    if app_env == "production" and not env.get("FRONTEND_ORIGINS", "").strip():
        raise RuntimeError("FRONTEND_ORIGINS must be explicitly configured in production.")
    if not values or "*" in values:
        raise RuntimeError("FRONTEND_ORIGINS must contain explicit origins; wildcard origins are not supported.")
    for origin in values:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != ""
            or "*" in origin
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError("Each FRONTEND_ORIGINS entry must be an HTTP(S) origin without a path or credentials.")
        try:
            parsed.port
        except ValueError as exc:
            raise RuntimeError("Each FRONTEND_ORIGINS entry must have a valid port.") from exc
        if app_env == "production" and parsed.scheme != "https":
            raise RuntimeError("Production frontend origins must use HTTPS.")
    return values


@dataclass(frozen=True)
class Settings:
    app_env: str
    frontend_origins: tuple[str, ...]
    session_hours: int
    starting_cash: Decimal
    fee_bps: Decimal
    slippage_bps: Decimal
    forex_fee_bps: Decimal
    forex_slippage_bps: Decimal
    max_order_value: Decimal
    max_exposure_percent: Decimal
    simulator_kill_switch: bool
    strategy_execution_enabled: bool


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    source = os.environ if env is None else env
    app_env = source.get("APP_ENV", "development").strip().lower()
    if app_env not in {"development", "test", "production"}:
        raise RuntimeError("APP_ENV must be development, test, or production.")
    return Settings(
        app_env=app_env,
        frontend_origins=_origins(source, app_env),
        session_hours=_integer(source, "SESSION_HOURS", "12", 1, 720),
        starting_cash=_decimal(source, "SIM_STARTING_CASH", "100000.00", Decimal("1"), Decimal("1000000000")),
        fee_bps=_decimal(source, "SIM_FEE_BPS", "10", Decimal("0"), Decimal("1000")),
        slippage_bps=_decimal(source, "SIM_SLIPPAGE_BPS", "5", Decimal("0"), Decimal("1000")),
        forex_fee_bps=_decimal(source, "SIM_FOREX_FEE_BPS", "10", Decimal("0"), Decimal("1000")),
        forex_slippage_bps=_decimal(source, "SIM_FOREX_SLIPPAGE_BPS", "5", Decimal("0"), Decimal("1000")),
        max_order_value=_decimal(source, "SIM_MAX_ORDER_VALUE", "25000", Decimal("1"), Decimal("100000000")),
        max_exposure_percent=_decimal(
            source, "SIM_MAX_EXPOSURE_PERCENT", "90", Decimal("1"), Decimal("100")
        ),
        simulator_kill_switch=_boolean(source, "SIMULATOR_KILL_SWITCH", "false"),
        strategy_execution_enabled=_boolean(source, "STRATEGY_EXECUTION_ENABLED", "false"),
    )


SETTINGS = load_settings()


def simulator_kill_switch_active() -> bool:
    """Read the switch dynamically so operators can stop execution without a restart."""
    return os.getenv("SIMULATOR_KILL_SWITCH", "false").strip().lower() != "false"


def strategy_worker_enabled() -> bool:
    """Worker is opt-in; malformed values fail closed."""
    return os.getenv("STRATEGY_EXECUTION_ENABLED", "false").strip().lower() == "true"


def production_paper_trading_enabled() -> bool:
    """Production paper orders require a separate explicit switch; no live orders exist."""
    return (
        os.getenv("APP_ENV", "development").strip().lower() != "production"
        or os.getenv("PAPER_TRADING_ENABLED", "false").strip().lower() == "true"
    )
