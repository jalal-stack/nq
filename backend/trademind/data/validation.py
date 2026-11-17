"""OHLCV normalization and data-quality checks.

Every frame that reaches indicators, agents or the risk engine should pass
through `normalize_ohlcv` and carry a `DataQualityReport`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
from pydantic import BaseModel

from trademind.data.base import OHLCV_COLUMNS
from trademind.domain import Timeframe


class DataQualityReport(BaseModel):
    rows: int
    duplicates_removed: int
    invalid_rows_removed: int
    missing_candles: int
    gaps: list[tuple[datetime, datetime]]
    last_ts: datetime | None
    age_seconds: float | None
    is_stale: bool

    @property
    def ok(self) -> bool:
        return self.rows > 0 and not self.is_stale


def normalize_ohlcv(df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Return (clean frame, duplicates removed, invalid rows removed).

    Index is coerced to a sorted, unique, tz-aware UTC DatetimeIndex.
    """
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    out = df[OHLCV_COLUMNS].astype(float).copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out.index, utc=True))
    out.index = idx.rename("ts")
    out = out.sort_index()

    dup_mask = out.index.duplicated(keep="last")
    duplicates = int(dup_mask.sum())
    out = out[~dup_mask]

    prices = out[["open", "high", "low", "close"]]
    valid = (
        prices.notna().all(axis=1)
        & (prices > 0).all(axis=1)
        & (out["high"] >= prices[["open", "close"]].max(axis=1))
        & (out["low"] <= prices[["open", "close"]].min(axis=1))
        & (out["volume"].fillna(0) >= 0)
        & np.isfinite(prices).all(axis=1)
    )
    invalid = int((~valid).sum())
    out = out[valid]
    out["volume"] = out["volume"].fillna(0.0)
    return out, duplicates, invalid


def find_gaps(
    index: pd.DatetimeIndex, timeframe: Timeframe, *, continuous: bool = True
) -> tuple[int, list[tuple[datetime, datetime]]]:
    """Count missing candles. For non-continuous markets (stocks, forex weekends)
    only gaps inside a trading day are counted; session-closure gaps are ignored."""
    if len(index) < 2:
        return 0, []
    step = pd.Timedelta(seconds=timeframe.seconds)
    deltas = index[1:] - index[:-1]
    missing = 0
    gaps: list[tuple[datetime, datetime]] = []
    for prev, cur, delta in zip(index[:-1], index[1:], deltas):
        if delta <= step:
            continue
        if not continuous and (timeframe == Timeframe.D1 or prev.date() != cur.date()):
            continue
        n = int(delta / step) - 1
        if n > 0:
            missing += n
            gaps.append((prev.to_pydatetime(), cur.to_pydatetime()))
    return missing, gaps


def assess(
    raw: pd.DataFrame,
    timeframe: Timeframe,
    *,
    continuous: bool = True,
    max_age_seconds: float | None = None,
    now: datetime | None = None,
) -> tuple[pd.DataFrame, DataQualityReport]:
    clean, dups, invalid = normalize_ohlcv(raw)
    missing, gaps = find_gaps(clean.index, timeframe, continuous=continuous)
    last_ts = clean.index[-1].to_pydatetime() if len(clean) else None
    now = now or datetime.now(timezone.utc)
    age = (now - last_ts).total_seconds() if last_ts else None
    # A candle is stamped at its open, so allow one full bar beyond the threshold.
    threshold = (max_age_seconds or 0) + timeframe.seconds
    stale = age is None or (max_age_seconds is not None and age > threshold)
    return clean, DataQualityReport(
        rows=len(clean),
        duplicates_removed=dups,
        invalid_rows_removed=invalid,
        missing_candles=missing,
        gaps=gaps,
        last_ts=last_ts,
        age_seconds=age,
        is_stale=stale,
    )
