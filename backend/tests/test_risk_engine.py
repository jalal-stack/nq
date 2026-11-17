from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from trademind.domain import AssetClass, Instrument, Side
from trademind.risk.engine import (
    CheckCode, MarketContext, OpenPosition, PortfolioState, RiskEngine, TradeProposal, session_open,
)

NOW = datetime(2026, 1, 6, 15, 0, tzinfo=timezone.utc)  # Tuesday, US session open
BTC = Instrument(symbol="BTC/USDT", asset_class=AssetClass.CRYPTO, correlation_group="crypto")


def pf(equity="5000", peak=None, day=None, positions=()):
    return PortfolioState(equity=D(equity), peak_equity=D(peak or equity), day_start_equity=D(day or equity),
                          positions=list(positions))


def ctx(age_s=60, atr="1000"):
    return MarketContext(as_of=NOW, last_data_ts=NOW - timedelta(seconds=age_s), atr=D(atr), spread_bps=D("2"))


def prop(entry="50000", stop="48000", side=Side.BUY, inst=BTC, tp="54000"):
    return TradeProposal(instrument=inst, side=side, entry_price=D(entry), stop_loss=D(stop),
                         take_profit=D(tp) if tp else None, strategy="t")


def failed(decision):
    return {c.code for c in decision.rejections}


def test_fixed_fractional_sizing_capped_by_notional():
    d = RiskEngine().evaluate(prop(), pf(), ctx())
    assert d.approved
    # 1% of 5000 = 50 risk / 2000 per unit = 0.025, but 25% notional cap = 1250/50000 = 0.025
    assert d.quantity == D("0.025") and d.risk_amount <= D("50")
    assert d.reward_risk == D("2.00")


def test_notional_cap_reduces_size():
    d = RiskEngine().evaluate(prop(stop="49500"), pf(), ctx(atr="500"))
    assert d.approved and d.quantity * D("50000") <= D("1250")
    assert any(c.code == CheckCode.SIZE_REDUCED for c in d.checks)


def test_stop_on_wrong_side_rejected():
    d = RiskEngine().evaluate(prop(stop="51000"), pf(), ctx())
    assert not d.approved and CheckCode.STOP_SIDE in failed(d) and d.quantity == 0


def test_stale_data_and_volatility_rejected():
    assert CheckCode.STALE_DATA in failed(RiskEngine().evaluate(prop(), pf(), ctx(age_s=3600)))
    d = RiskEngine().evaluate(prop(stop="45000"), pf(), ctx(atr="6000"))
    assert CheckCode.ABNORMAL_VOLATILITY in failed(d)


def test_daily_loss_and_drawdown_halt_trading():
    assert CheckCode.DAILY_LOSS in failed(RiskEngine().evaluate(prop(), pf("4800", day="5000"), ctx()))
    assert CheckCode.MAX_DRAWDOWN in failed(RiskEngine().evaluate(prop(), pf("4000", peak="5000", day="4000"), ctx()))


def test_duplicate_and_correlated_positions_rejected():
    eth = OpenPosition(symbol="ETH/USDT", side=Side.BUY, quantity=D("0.1"), entry_price=D("3000"),
                       mark_price=D("3000"), correlation_group="crypto")
    sol = eth.model_copy(update={"symbol": "SOL/USDT"})
    d = RiskEngine().evaluate(prop(), pf(positions=[eth, sol]), ctx())
    assert CheckCode.CORRELATED_POSITIONS in failed(d)
    btc = eth.model_copy(update={"symbol": "BTC/USDT"})
    assert CheckCode.DUPLICATE_POSITION in failed(RiskEngine().evaluate(prop(), pf(positions=[btc]), ctx()))


def test_sessions():
    assert session_open(AssetClass.CRYPTO, datetime(2026, 1, 10, 3, tzinfo=timezone.utc))
    assert not session_open(AssetClass.STOCK, datetime(2026, 1, 10, 15, tzinfo=timezone.utc))  # Saturday
    assert session_open(AssetClass.STOCK, NOW)
    assert not session_open(AssetClass.FOREX, datetime(2026, 1, 10, 12, tzinfo=timezone.utc))
    aapl = Instrument(symbol="AAPL", asset_class=AssetClass.STOCK, lot_size=D("1"))
    night = MarketContext(as_of=datetime(2026, 1, 6, 3, tzinfo=timezone.utc),
                          last_data_ts=datetime(2026, 1, 6, 3, tzinfo=timezone.utc), atr=D("2"))
    d = RiskEngine().evaluate(prop("200", "195", inst=aapl, tp=None), pf(), night)
    assert CheckCode.SESSION_CLOSED in failed(d)


def test_whole_share_lot_rounding():
    aapl = Instrument(symbol="AAPL", asset_class=AssetClass.STOCK, lot_size=D("1"))
    d = RiskEngine().evaluate(prop("200", "195", inst=aapl, tp=None), pf(), ctx(atr="2"))
    assert d.approved and d.quantity == D("6")  # 1250/200 = 6.25 -> 6 shares
