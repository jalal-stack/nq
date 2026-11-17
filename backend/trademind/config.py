from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRADEMIND_", env_file=".env", extra="ignore")

    environment: Literal["dev", "test", "prod"] = "dev"
    base_currency: str = "USD"
    starting_equity: Decimal = Field(default=Decimal("5000"), gt=0)

    # Hard safety switch. Validated to always be "paper": there is no live execution path.
    trading_mode: Literal["paper"] = "paper"

    # Risk defaults (fractions of equity unless noted)
    max_risk_per_trade: Decimal = Decimal("0.01")
    max_daily_loss: Decimal = Decimal("0.03")
    max_drawdown: Decimal = Decimal("0.15")
    max_gross_exposure: Decimal = Decimal("1.0")
    max_position_notional: Decimal = Decimal("0.25")
    max_open_positions: int = 5
    max_correlated_positions: int = 2
    max_data_age_seconds: int = 900

    @field_validator("trading_mode", mode="before")
    @classmethod
    def _paper_only(cls, v: str) -> str:
        if v != "paper":
            raise ValueError("Only paper trading is supported; live trading is disabled.")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
