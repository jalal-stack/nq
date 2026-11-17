"""Shared domain types used across data, risk, execution and agents."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class AssetClass(StrEnum):
    CRYPTO = "crypto"
    STOCK = "stock"
    FOREX = "forex"


class TradingStyle(StrEnum):
    SCALPING = "scalping"
    INTRADAY = "intraday"
    SWING = "swing"


class Timeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

    @property
    def seconds(self) -> int:
        return {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}[self.value]


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(StrEnum):
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


def ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


class Instrument(BaseModel):
    symbol: str
    asset_class: AssetClass
    quote_currency: str = "USD"
    tick_size: Decimal = Decimal("0.00000001")
    lot_size: Decimal = Decimal("0.00000001")
    min_notional: Decimal = Decimal("1")
    correlation_group: str | None = None  # e.g. "crypto-majors", "usd-pairs"


class Candle(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = Field(ge=0)

    @field_validator("ts")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)

    @model_validator(mode="after")
    def _ohlc_consistent(self) -> "Candle":
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("prices must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("inconsistent OHLC")
        return self


class Quote(BaseModel):
    symbol: str
    ts: datetime
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)

    @model_validator(mode="after")
    def _spread(self) -> "Quote":
        if self.ask < self.bid:
            raise ValueError("ask below bid")
        return self

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_bps(self) -> float:
        return (self.ask - self.bid) / self.mid * 10_000
