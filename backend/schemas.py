"""Validated API request and response models."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class TradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_type: Literal["EQUITY", "FOREX"] = "EQUITY"
    symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.:/_&-]+$")
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0, le=10_000_000)


class WatchlistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_type: Literal["EQUITY", "FOREX"]
    symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.:/_&-]+$")


class HistoricalCandleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_type: Literal["EQUITY", "FOREX"]
    symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.:/_&-]+$")
    timestamp: datetime
    open: float = Field(gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    high: float = Field(gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    low: float = Field(gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    close: float = Field(gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    base_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    quote_currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def validate_historical_candle(self):
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("Historical candle timestamps must include a timezone.")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("Historical candle high/low must contain the open and close.")
        if self.low > self.high:
            raise ValueError("Historical candle low cannot exceed its high.")
        if self.market_type == "EQUITY" and self.quote_currency != "INR":
            raise ValueError("Indian equity historical candles must be INR-denominated.")
        if self.market_type == "FOREX":
            if not self.base_currency or self.symbol != f"{self.base_currency}/{self.quote_currency}":
                raise ValueError("Forex candle symbols must match their BASE/QUOTE currencies.")
        return self


class HistoricalNewsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)
    source: str | None = Field(default=None, max_length=120)
    url: str | None = Field(default=None, max_length=500)
    published_at: datetime

    @model_validator(mode="after")
    def validate_publication_time(self):
        if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
            raise ValueError("Historical news publication times must include a timezone.")
        return self


class HistoricalBacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str = Field(min_length=1, max_length=100)
    data_rights_confirmed: Literal[True]
    strategy_version: int | None = Field(default=None, ge=0)
    starting_cash: float = Field(gt=0, le=1_000_000_000, allow_inf_nan=False)
    candles: list[HistoricalCandleInput] = Field(min_length=2, max_length=20_000)
    news: list[HistoricalNewsInput] = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_dataset(self):
        seen = set()
        for candle in self.candles:
            key = (
                candle.market_type,
                candle.symbol.strip().upper(),
                candle.timestamp.astimezone(timezone.utc).isoformat(),
            )
            if key in seen:
                raise ValueError("Historical dataset contains duplicate candles for the same instrument and time.")
            seen.add(key)
        return self


class ResetPortfolioRequest(BaseModel):
    confirmation: Literal["RESET VIRTUAL PORTFOLIO"]


class PasswordConfirmation(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class StrategyConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    min_confidence: float = Field(ge=0.5, le=0.95)
    max_event_age_hours: int = Field(ge=1, le=168)
    max_position_percent: float = Field(gt=0, le=25)
    max_portfolio_exposure_percent: float = Field(gt=0, le=90)
    cooldown_minutes: int = Field(ge=0, le=1440)
    daily_loss_limit_percent: float = Field(default=5, gt=0, le=20)
