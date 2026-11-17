from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from trademind.api.main import app
from trademind.backtest.engine import EmaRsiAtrStrategy, run_backtest
from trademind.data.providers import SyntheticProvider
from trademind.domain import AssetClass, Candle, Instrument, OrderStatus, OrderType, Side, Timeframe
from trademind.execution.paper import CostModel, PaperBroker
from trademind.performance.metrics import evaluate, max_drawdown

T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
NO_COSTS = CostModel(fee_bps=0, spread_bps=0, slippage_bps=0, max_participation=1)


def bar(i, o, h, l, c, v=1000.0):
    return Candle(ts=T0 + timedelta(hours=i), open=o, high=h, low=l, close=c, volume=v)


def test_market_order_fills_next_bar_with_costs():
    b = PaperBroker(5000, CostModel(fee_bps=10, spread_bps=4, slippage_bps=1, max_participation=1))
    o = b.submit("X", Side.BUY, 10, T0)
    b.on_bar("X", bar(0, 100, 101, 99, 100))  # same bar as submission: no fill
    assert o.status == OrderStatus.PENDING
    b.on_bar("X", bar(1, 100, 101, 99, 100))
    assert o.status == OrderStatus.FILLED
    assert o.avg_fill_price == pytest.approx(100 * (1 + 3 / 10_000))
    assert o.fees == pytest.approx(10 * o.avg_fill_price * 0.001)
    assert b.cash == pytest.approx(5000 - 10 * o.avg_fill_price - o.fees)


def test_limit_order_partial_fill_then_expiry():
    b = PaperBroker(5000, CostModel(fee_bps=0, spread_bps=0, slippage_bps=0, max_participation=0.1))
    o = b.submit("X", Side.BUY, 30, T0, OrderType.LIMIT, limit_price=95, expires_at=T0 + timedelta(hours=3))
    b.on_bar("X", bar(1, 100, 101, 96, 97))  # not reached
    assert o.filled_qty == 0
    b.on_bar("X", bar(2, 96, 97, 94, 95, v=100))  # 10% of 100 = 10
    assert o.status == OrderStatus.PARTIALLY_FILLED and o.filled_qty == 10 and o.avg_fill_price == 95
    b.on_bar("X", bar(3, 95, 96, 94, 95, v=100))
    assert o.status == OrderStatus.EXPIRED and o.filled_qty == 10
    assert [e.status for e in o.events][-1] == OrderStatus.EXPIRED


def test_rejections():
    b = PaperBroker(1000, NO_COSTS)
    assert b.submit("X", Side.BUY, 1, T0, OrderType.LIMIT).status == OrderStatus.REJECTED
    o = b.submit("X", Side.BUY, 100, T0)
    b.on_bar("X", bar(1, 100, 101, 99, 100))
    assert o.status == OrderStatus.REJECTED and "buying power" in o.events[-1].detail


def test_stop_loss_and_take_profit_round_trips():
    b = PaperBroker(5000, NO_COSTS)
    b.submit("X", Side.BUY, 10, T0, stop_loss=95, take_profit=110)
    b.on_bar("X", bar(1, 100, 101, 99, 100))
    b.on_bar("X", bar(2, 100, 111, 99, 108))
    assert b.trades[-1].exit_reason == "take_profit" and b.trades[-1].pnl == pytest.approx(100)
    b.submit("X", Side.BUY, 10, T0 + timedelta(hours=2), stop_loss=95, take_profit=110)
    b.on_bar("X", bar(3, 100, 101, 99, 100))
    b.on_bar("X", bar(4, 93, 94, 90, 91))  # gap through stop fills at open
    assert b.trades[-1].exit_reason == "stop_loss" and b.trades[-1].exit_price == 93
    assert b.equity == pytest.approx(5000 + 100 - 70) and not b.positions


def test_short_position_pnl():
    b = PaperBroker(5000, NO_COSTS)
    b.submit("X", Side.SELL, 10, T0)
    b.on_bar("X", bar(1, 100, 100, 100, 100))
    b.submit("X", Side.BUY, 10, T0 + timedelta(hours=1))
    b.on_bar("X", bar(2, 90, 90, 90, 90))
    assert b.trades[-1].pnl == pytest.approx(100) and b.equity == pytest.approx(5100)


def test_metrics():
    assert max_drawdown([100, 120, 90, 130]) == pytest.approx(0.25)
    r = evaluate([], [])
    assert r.trades == 0 and r.win_rate is None and r.sample_warning


def test_backtest_is_deterministic_and_respects_risk():
    end = datetime(2026, 3, 1, tzinfo=timezone.utc)
    df = SyntheticProvider(end=end).fetch_ohlcv("SYN", Timeframe.H1, limit=1500)
    inst = Instrument(symbol="SYN", asset_class=AssetClass.CRYPTO)
    r1 = run_backtest(df, inst, EmaRsiAtrStrategy())
    r2 = run_backtest(df, inst, EmaRsiAtrStrategy())
    assert r1 == r2 and r1.signals > 0 and r1.report.trades > 0
    # Each loss is bounded by ~1% risk plus gap/costs.
    assert r1.report.average_loss is None or r1.report.average_loss > -5000 * 0.02


def test_api():
    c = TestClient(app)
    h = c.get("/health").json()
    assert h["trading_mode"] == "paper" and h["live_trading_enabled"] is False
    r = c.get("/market/synthetic/ohlcv", params={"symbol": "SYN", "limit": 250, "indicators": True})
    assert r.status_code == 200 and len(r.json()["candles"]) == 250 and not r.json()["realtime"]
    assert c.get("/market/nope/ohlcv", params={"symbol": "X"}).status_code == 404
    assert c.post("/backtest", json={"bars": 800}).status_code == 200
    body = {
        "proposal": {"instrument": {"symbol": "BTC", "asset_class": "crypto"}, "side": "buy",
                     "entry_price": "100", "stop_loss": "101", "strategy": "t"},
        "portfolio": {"equity": "5000", "peak_equity": "5000", "day_start_equity": "5000"},
        "context": {"as_of": "2026-01-06T15:00:00Z", "last_data_ts": "2026-01-06T14:59:00Z"},
    }
    d = c.post("/risk/evaluate", json=body).json()
    assert d["approved"] is False and any(x["code"] == "stop_side" and not x["passed"] for x in d["checks"])
