"""Unified market data abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd

from trademind.domain import AssetClass, Quote, Timeframe

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class ProviderError(RuntimeError):
    pass


class MarketDataProvider(ABC):
    """Adapters return a DataFrame indexed by UTC timestamp with OHLCV_COLUMNS."""

    name: str
    asset_classes: frozenset[AssetClass]
    # Free/unofficial sources must not be presented as real-time institutional data.
    realtime: bool = False

    @abstractmethod
    def fetch_ohlcv(
        self, symbol: str, timeframe: Timeframe, start: datetime | None = None, limit: int = 500
    ) -> pd.DataFrame: ...

    def fetch_quote(self, symbol: str) -> Quote | None:
        return None
