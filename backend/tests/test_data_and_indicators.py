from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from trademind.config import Settings
from trademind.data.providers import SyntheticProvider
from trademind.data.validation import assess, find_gaps, normalize_ohlcv
from trademind.domain import Candle, Timeframe
from trademind import indicators as ind

T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)  # a Monday


def frame(closes, start=T0, step=timedelta(hours=1), volume=1000.0):
    idx = pd.date_range(start, periods=len(closes), freq=step, tz="UTC")
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999, "close": c, "volume": volume}, index=idx)


def test_live_trading_cannot_be_enabled():
    with pytest.raises(ValueError):
        Settings(trading_mode="live")


def test_candle_rejects_inconsistent_ohlc():
    with pytest.raises(ValueError):
        Candle(ts=T0, open=10, high=9, low=8, close=10, volume=1)


def test_normalize_removes_duplicates_invalid_and_converts_timezone():
    df = frame([100, 101, 102, 103])
    df = pd.concat([df, df.iloc[[1]]])
    df.iloc[2, df.columns.get_loc("high")] = 1  # high below open/close
    df.index = df.index.tz_convert("America/New_York")
    clean, dups, invalid = normalize_ohlcv(df)
    assert dups == 1 and invalid == 1 and len(clean) == 3
    assert str(clean.index.tz) == "UTC" and clean.index.is_monotonic_increasing


def test_missing_candles_detected_and_session_gaps_ignored():
    df = frame(range(100, 110)).drop(index=frame(range(100, 110)).index[[3, 4]])
    missing, gaps = find_gaps(df.index, Timeframe.H1)
    assert missing == 2 and len(gaps) == 1
    overnight = pd.DatetimeIndex(["2026-01-05 20:00", "2026-01-06 14:00"], tz="UTC")
    assert find_gaps(overnight, Timeframe.H1, continuous=False)[0] == 0
    assert find_gaps(overnight, Timeframe.H1, continuous=True)[0] == 17


def test_stale_data_flag():
    df = frame([100] * 5)
    now = df.index[-1] + timedelta(hours=3)
    _, rep = assess(df, Timeframe.H1, max_age_seconds=900, now=now.to_pydatetime())
    assert rep.is_stale and not rep.ok
    _, rep = assess(df, Timeframe.H1, max_age_seconds=900, now=(df.index[-1] + timedelta(minutes=30)).to_pydatetime())
    assert not rep.is_stale


def test_synthetic_provider_is_deterministic_and_valid():
    end = datetime(2026, 1, 10, tzinfo=timezone.utc)
    a = SyntheticProvider(end=end).fetch_ohlcv("BTC/USDT", Timeframe.H1, limit=200)
    b = SyntheticProvider(end=end).fetch_ohlcv("BTC/USDT", Timeframe.H1, limit=200)
    pd.testing.assert_frame_equal(a, b)
    _, dups, invalid = normalize_ohlcv(a)
    assert dups == 0 and invalid == 0


def test_indicator_reference_values():
    close = pd.Series([1.0, 2, 3, 4, 5])
    # EMA(3) seeded at first value with alpha 0.5: last value 4.0625
    assert ind.ema(close, 3).iloc[-1] == pytest.approx(4.0625)
    assert ind.rsi(pd.Series(range(1, 40), dtype=float)).iloc[-1] == 100.0
    flat = frame([100.0] * 60)
    assert ind.atr(flat).iloc[-1] == pytest.approx(0.2, rel=1e-6)
    bb = ind.bollinger(flat["close"])
    assert bb["bb_upper"].iloc[-1] == pytest.approx(100.0)


def test_vwap_resets_each_day_and_compute_all_columns():
    df = frame([100.0] * 30)
    v = ind.vwap(df)
    assert v.iloc[0] == pytest.approx((100.1 + 99.9 + 100) / 3)
    out = ind.compute_all(SyntheticProvider().fetch_ohlcv("X", Timeframe.H1, limit=300))
    for col in ["ema_9", "ema_200", "rsi_14", "macd", "signal", "bb_upper", "adx", "atr_14", "vwap"]:
        assert col in out and out[col].iloc[-1] == out[col].iloc[-1]  # not NaN
    assert 0 <= out["rsi_14"].dropna().min() and out["rsi_14"].max() <= 100
