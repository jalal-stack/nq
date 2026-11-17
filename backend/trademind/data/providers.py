"""Provider adapters. Third-party libraries are imported lazily so the core
runs and tests without network access or optional dependencies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from trademind.data.base import OHLCV_COLUMNS, MarketDataProvider, ProviderError
from trademind.domain import AssetClass, Quote, Timeframe


class CCXTProvider(MarketDataProvider):
    """Public (unauthenticated) exchange data via CCXT. No API keys are used."""

    name = "ccxt"
    asset_classes = frozenset({AssetClass.CRYPTO})
    realtime = True

    def __init__(self, exchange_id: str = "binance") -> None:
        try:
            import ccxt  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise ProviderError("ccxt not installed: pip install 'trademind[providers]'") from e
        self.exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})

    def fetch_ohlcv(self, symbol, timeframe, start=None, limit=500):  # pragma: no cover - network
        since = int(start.timestamp() * 1000) if start else None
        rows = self.exchange.fetch_ohlcv(symbol, timeframe.value, since=since, limit=limit)
        df = pd.DataFrame(rows, columns=["ts", *OHLCV_COLUMNS])
        df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
        return df

    def fetch_quote(self, symbol):  # pragma: no cover - network
        t = self.exchange.fetch_ticker(symbol)
        if not t.get("bid") or not t.get("ask"):
            return None
        ts = datetime.fromtimestamp(t["timestamp"] / 1000, tz=timezone.utc)
        return Quote(symbol=symbol, ts=ts, bid=t["bid"], ask=t["ask"])


class YFinanceProvider(MarketDataProvider):
    """Yahoo Finance via the unofficial yfinance library.

    Delayed, best-effort data for research only; not an institutional or real-time feed,
    and subject to Yahoo's terms of use. Intraday history is limited by Yahoo.
    """

    name = "yfinance"
    asset_classes = frozenset({AssetClass.STOCK, AssetClass.FOREX})
    realtime = False

    def fetch_ohlcv(self, symbol, timeframe, start=None, limit=500):  # pragma: no cover - network
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ImportError as e:
            raise ProviderError("yfinance not installed: pip install 'trademind[providers]'") from e
        interval = {"4h": "1h"}.get(timeframe.value, timeframe.value)
        start = start or datetime.now(timezone.utc) - timedelta(seconds=timeframe.seconds * limit)
        df = yf.Ticker(symbol).history(interval=interval, start=start, auto_adjust=False)
        if df.empty:
            raise ProviderError(f"no data for {symbol}")
        df = df.rename(columns=str.lower)[OHLCV_COLUMNS]
        return df.tail(limit)


class SyntheticProvider(MarketDataProvider):
    """Deterministic geometric random walk for tests, demos and offline development."""

    name = "synthetic"
    asset_classes = frozenset(AssetClass)
    realtime = False

    def __init__(self, seed: int = 7, start_price: float = 100.0, vol: float = 0.01,
                 end: datetime | None = None) -> None:
        self.seed, self.start_price, self.vol = seed, start_price, vol
        self.end = end

    def fetch_ohlcv(self, symbol, timeframe, start=None, limit=500):
        rng = np.random.default_rng(self.seed + sum(map(ord, symbol)))
        end = self.end or datetime.now(timezone.utc).replace(second=0, microsecond=0)
        idx = pd.date_range(end=end, periods=limit, freq=pd.Timedelta(seconds=timeframe.seconds), tz="UTC")
        rets = rng.normal(0, self.vol, limit)
        close = self.start_price * np.exp(np.cumsum(rets))
        open_ = np.concatenate([[self.start_price], close[:-1]])
        wick = np.abs(rng.normal(0, self.vol / 2, limit)) * close
        high = np.maximum(open_, close) + wick
        low = np.maximum(np.minimum(open_, close) - wick, 1e-9)
        volume = rng.lognormal(10, 0.5, limit)
        return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)

    def fetch_quote(self, symbol):
        last = self.fetch_ohlcv(symbol, Timeframe.M1, limit=2).iloc[-1]
        half = last.close * 0.0002
        return Quote(symbol=symbol, ts=datetime.now(timezone.utc), bid=last.close - half, ask=last.close + half)
