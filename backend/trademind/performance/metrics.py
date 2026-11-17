"""Performance statistics computed from closed trades and an equity curve.

Ratios are reported as `None` when the sample cannot support them (e.g. no losing
trades for profit factor, fewer than two returns for Sharpe) rather than as
infinities or misleading zeros.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from trademind.execution.paper import ClosedTrade


class PerformanceReport(BaseModel):
    trades: int
    net_profit: float
    total_fees: float
    win_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    average_win: float | None
    average_loss: float | None
    max_drawdown: float  # fraction of peak equity
    sharpe: float | None
    sortino: float | None
    trades_per_day: float | None
    exposure: float | None  # fraction of time with an open position
    sample_warning: str | None


def max_drawdown(equity: Sequence[float]) -> float:
    if len(equity) == 0:
        return 0.0
    arr = np.asarray(equity, dtype=float)
    peaks = np.maximum.accumulate(arr)
    return float(np.max((peaks - arr) / peaks))


def _ratio(returns: np.ndarray, periods_per_year: float, downside: bool) -> float | None:
    if len(returns) < 2:
        return None
    mean = returns.mean()
    if downside:
        neg = np.minimum(returns, 0)
        dev = math.sqrt(float((neg**2).mean()))
    else:
        dev = float(returns.std(ddof=1))
    if dev == 0:
        return None
    return float(mean / dev * math.sqrt(periods_per_year))


def evaluate(
    trades: Sequence[ClosedTrade],
    equity_curve: Sequence[tuple[datetime, float]],
    periods_per_year: float = 365,
) -> PerformanceReport:
    pnls = np.array([t.pnl for t in trades], dtype=float)
    wins, losses = pnls[pnls > 0], pnls[pnls < 0]
    equity = [e for _, e in equity_curve]
    rets = np.diff(equity) / np.asarray(equity[:-1]) if len(equity) > 1 else np.array([])

    trades_per_day = exposure = None
    if len(equity_curve) > 1:
        span_days = (equity_curve[-1][0] - equity_curve[0][0]).total_seconds() / 86400
        if span_days > 0:
            trades_per_day = len(trades) / span_days
            held = sum((t.exit_ts - t.entry_ts).total_seconds() for t in trades) / 86400
            exposure = min(held / span_days, 1.0)

    n = len(pnls)
    warning = None
    if n < 30:
        warning = f"only {n} trades: statistics are not reliable evidence of an edge"
    return PerformanceReport(
        trades=n,
        net_profit=float(pnls.sum()) if n else 0.0,
        total_fees=float(sum(t.fees for t in trades)),
        win_rate=float(len(wins) / n) if n else None,
        profit_factor=float(wins.sum() / -losses.sum()) if len(losses) else None,
        expectancy=float(pnls.mean()) if n else None,
        average_win=float(wins.mean()) if len(wins) else None,
        average_loss=float(losses.mean()) if len(losses) else None,
        max_drawdown=max_drawdown(equity),
        sharpe=_ratio(rets, periods_per_year, downside=False),
        sortino=_ratio(rets, periods_per_year, downside=True),
        trades_per_day=trades_per_day,
        exposure=exposure,
        sample_warning=warning,
    )
