"""Event-driven backtester that routes every signal through the same Risk Engine
and PaperBroker used for paper trading, so backtests and paper trading share rules.

Signals are computed on bar t's close and can only fill from bar t+1 (no look-ahead).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

import pandas as pd
from pydantic import BaseModel

from trademind.domain import Candle, Instrument, OrderType, Side
from trademind.execution.paper import CostModel, PaperBroker
from trademind.indicators import compute_all
from trademind.performance.metrics import PerformanceReport, evaluate
from trademind.risk.engine import (
    MarketContext, OpenPosition, PortfolioState, RiskEngine, RiskLimits, TradeProposal,
)


class Signal(BaseModel):
    side: Side
    stop_loss: float
    take_profit: float | None = None


class Strategy(Protocol):
    name: str
    warmup: int

    def signal(self, history: pd.DataFrame) -> Signal | None:
        """`history` ends at the current (closed) bar and includes indicator columns."""


class EmaRsiAtrStrategy:
    """Baseline: long-only EMA(20/50) cross filtered by RSI, ATR-based stop and target."""

    name = "ema_rsi_atr_v1"
    warmup = 60

    def __init__(self, stop_atr: float = 2.0, target_atr: float = 3.0) -> None:
        self.stop_atr, self.target_atr = stop_atr, target_atr

    def signal(self, h: pd.DataFrame) -> Signal | None:
        cur, prev = h.iloc[-1], h.iloc[-2]
        crossed = prev.ema_20 <= prev.ema_50 and cur.ema_20 > cur.ema_50
        if crossed and 50 < cur.rsi_14 < 70 and cur.atr_14 > 0:
            return Signal(side=Side.BUY, stop_loss=cur.close - self.stop_atr * cur.atr_14,
                          take_profit=cur.close + self.target_atr * cur.atr_14)
        return None


class BacktestResult(BaseModel):
    strategy: str
    symbol: str
    bars: int
    signals: int
    risk_rejections: dict[str, int]
    report: PerformanceReport


def run_backtest(
    df: pd.DataFrame,
    instrument: Instrument,
    strategy: Strategy,
    starting_cash: float = 5000.0,
    costs: CostModel | None = None,
    limits: RiskLimits | None = None,
    periods_per_year: float = 365,
) -> BacktestResult:
    data = compute_all(df)
    broker = PaperBroker(starting_cash=starting_cash, costs=costs or CostModel())
    engine = RiskEngine(limits or RiskLimits(max_data_age_seconds=10**9))
    peak = day_start = starting_cash
    current_day = None
    signals = 0
    rejections: dict[str, int] = {}

    for i, (ts, row) in enumerate(data.iterrows()):
        bar = Candle(ts=ts, open=row.open, high=row.high, low=row.low, close=row.close, volume=row.volume)
        broker.on_bar(instrument.symbol, bar)
        eq = broker.equity
        peak = max(peak, eq)
        if current_day != ts.date():
            current_day, day_start = ts.date(), eq
        if i < strategy.warmup or instrument.symbol in broker.positions:
            continue
        if any(o.is_open for o in broker.orders.values()):
            continue
        sig = strategy.signal(data.iloc[: i + 1])
        if sig is None:
            continue
        signals += 1
        proposal = TradeProposal(
            instrument=instrument, side=sig.side, entry_price=Decimal(str(row.close)),
            stop_loss=Decimal(str(sig.stop_loss)),
            take_profit=Decimal(str(sig.take_profit)) if sig.take_profit else None,
            strategy=strategy.name,
        )
        pf = PortfolioState(
            equity=Decimal(str(eq)), peak_equity=Decimal(str(peak)), day_start_equity=Decimal(str(day_start)),
            positions=[OpenPosition(symbol=p.symbol, side=p.side, quantity=Decimal(str(abs(p.quantity))),
                                    entry_price=Decimal(str(p.avg_price)), mark_price=Decimal(str(p.mark)),
                                    correlation_group=instrument.correlation_group)
                       for p in broker.positions.values()],
        )
        ctx = MarketContext(as_of=ts, last_data_ts=ts, atr=Decimal(str(row.atr_14)))
        decision = engine.evaluate(proposal, pf, ctx)
        if not decision.approved:
            for c in decision.rejections:
                rejections[c.code] = rejections.get(c.code, 0) + 1
            continue
        broker.submit(instrument.symbol, sig.side, float(decision.quantity), ts, OrderType.MARKET,
                      stop_loss=sig.stop_loss, take_profit=sig.take_profit, tag=strategy.name)

    return BacktestResult(
        strategy=strategy.name, symbol=instrument.symbol, bars=len(data), signals=signals,
        risk_rejections=rejections,
        report=evaluate(broker.trades, broker.equity_curve, periods_per_year),
    )
