"""Deterministic Risk Engine.

The engine is the final gate before user approval and paper execution. Its decision is
pure, rule-based and reproducible; no LLM output can override a rejection.
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from trademind.config import Settings
from trademind.domain import AssetClass, Instrument, Side, ensure_utc


class RiskLimits(BaseModel):
    max_risk_per_trade: Decimal = Decimal("0.01")
    max_daily_loss: Decimal = Decimal("0.03")
    max_drawdown: Decimal = Decimal("0.15")
    max_gross_exposure: Decimal = Decimal("1.0")
    max_position_notional: Decimal = Decimal("0.25")
    max_open_positions: int = 5
    max_correlated_positions: int = 2
    max_data_age_seconds: int = 900
    max_stop_distance: Decimal = Decimal("0.10")  # stop further than 10% from entry is rejected
    min_stop_distance_atr: Decimal = Decimal("0.5")  # stop tighter than 0.5 ATR is noise
    max_atr_pct: Decimal = Decimal("0.08")  # abnormal volatility threshold (ATR / price)
    max_spread_bps: Decimal = Decimal("50")

    @classmethod
    def from_settings(cls, s: Settings) -> "RiskLimits":
        return cls(**{k: getattr(s, k) for k in cls.model_fields if hasattr(s, k)})


class OpenPosition(BaseModel):
    symbol: str
    side: Side
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    correlation_group: str | None = None

    @property
    def notional(self) -> Decimal:
        return abs(self.quantity * self.mark_price)


class PortfolioState(BaseModel):
    equity: Decimal
    peak_equity: Decimal
    day_start_equity: Decimal
    positions: list[OpenPosition] = Field(default_factory=list)

    @property
    def gross_exposure(self) -> Decimal:
        return sum((p.notional for p in self.positions), Decimal(0))


class TradeProposal(BaseModel):
    """Structured proposal produced by the Strategy Agent (or a human)."""

    instrument: Instrument
    side: Side
    entry_price: Decimal = Field(gt=0)
    stop_loss: Decimal = Field(gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    strategy: str
    rationale: str = ""
    requested_quantity: Decimal | None = Field(default=None, gt=0)


class MarketContext(BaseModel):
    as_of: datetime
    last_data_ts: datetime
    atr: Decimal | None = None
    spread_bps: Decimal | None = None


class CheckCode(StrEnum):
    STOP_SIDE = "stop_side"
    STOP_TOO_WIDE = "stop_too_wide"
    STOP_TOO_TIGHT = "stop_too_tight"
    STALE_DATA = "stale_data"
    ABNORMAL_VOLATILITY = "abnormal_volatility"
    WIDE_SPREAD = "wide_spread"
    SESSION_CLOSED = "session_closed"
    DAILY_LOSS = "daily_loss"
    MAX_DRAWDOWN = "max_drawdown"
    MAX_OPEN_POSITIONS = "max_open_positions"
    CORRELATED_POSITIONS = "correlated_positions"
    DUPLICATE_POSITION = "duplicate_position"
    EXPOSURE = "exposure"
    SIZE_TOO_SMALL = "size_too_small"
    SIZE_REDUCED = "size_reduced"


class RiskCheck(BaseModel):
    code: CheckCode
    passed: bool
    detail: str


class RiskDecision(BaseModel):
    approved: bool
    quantity: Decimal
    notional: Decimal
    risk_amount: Decimal
    reward_risk: Decimal | None
    checks: list[RiskCheck]

    @property
    def rejections(self) -> list[RiskCheck]:
        return [c for c in self.checks if not c.passed]


# US equity regular session in UTC (14:30-21:00 covers EDT; EST shifts by +1h).
# Kept conservative and simple; holidays are not modelled.
_US_EQUITY_OPEN_UTC = (time(13, 30), time(21, 0))


def session_open(asset_class: AssetClass, at: datetime) -> bool:
    at = ensure_utc(at)
    if asset_class == AssetClass.CRYPTO:
        return True
    if asset_class == AssetClass.FOREX:
        # Closed from Friday 22:00 UTC to Sunday 22:00 UTC.
        wd, t = at.weekday(), at.time()
        return not (wd == 5 or (wd == 4 and t >= time(22)) or (wd == 6 and t < time(22)))
    if at.weekday() >= 5:
        return False
    start, end = _US_EQUITY_OPEN_UTC
    return start <= at.time() < end


class RiskEngine:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def evaluate(self, p: TradeProposal, pf: PortfolioState, ctx: MarketContext) -> RiskDecision:
        L = self.limits
        checks: list[RiskCheck] = []

        def add(code: CheckCode, ok: bool, detail: str) -> None:
            checks.append(RiskCheck(code=code, passed=ok, detail=detail))

        entry, stop = p.entry_price, p.stop_loss
        stop_ok = stop < entry if p.side == Side.BUY else stop > entry
        add(CheckCode.STOP_SIDE, stop_ok, f"stop {stop} vs entry {entry} for {p.side}")
        per_unit_risk = abs(entry - stop)
        stop_pct = per_unit_risk / entry
        add(CheckCode.STOP_TOO_WIDE, stop_pct <= L.max_stop_distance,
            f"stop distance {stop_pct:.4f} (max {L.max_stop_distance})")
        if ctx.atr is not None and ctx.atr > 0:
            add(CheckCode.STOP_TOO_TIGHT, per_unit_risk >= ctx.atr * L.min_stop_distance_atr,
                f"stop {per_unit_risk} vs {L.min_stop_distance_atr} ATR ({ctx.atr})")
            atr_pct = ctx.atr / entry
            add(CheckCode.ABNORMAL_VOLATILITY, atr_pct <= L.max_atr_pct,
                f"ATR/price {atr_pct:.4f} (max {L.max_atr_pct})")

        age = (ensure_utc(ctx.as_of) - ensure_utc(ctx.last_data_ts)).total_seconds()
        add(CheckCode.STALE_DATA, 0 <= age <= L.max_data_age_seconds,
            f"data age {age:.0f}s (max {L.max_data_age_seconds}s)")
        if ctx.spread_bps is not None:
            add(CheckCode.WIDE_SPREAD, ctx.spread_bps <= L.max_spread_bps,
                f"spread {ctx.spread_bps}bps (max {L.max_spread_bps})")
        add(CheckCode.SESSION_CLOSED, session_open(p.instrument.asset_class, ctx.as_of),
            f"{p.instrument.asset_class} session at {ensure_utc(ctx.as_of):%Y-%m-%d %H:%M} UTC")

        daily_loss = (pf.day_start_equity - pf.equity) / pf.day_start_equity
        add(CheckCode.DAILY_LOSS, daily_loss < L.max_daily_loss,
            f"daily loss {daily_loss:.4f} (max {L.max_daily_loss})")
        dd = (pf.peak_equity - pf.equity) / pf.peak_equity
        add(CheckCode.MAX_DRAWDOWN, dd < L.max_drawdown, f"drawdown {dd:.4f} (max {L.max_drawdown})")
        add(CheckCode.MAX_OPEN_POSITIONS, len(pf.positions) < L.max_open_positions,
            f"{len(pf.positions)} open (max {L.max_open_positions})")
        held = any(pos.symbol == p.instrument.symbol for pos in pf.positions)
        add(CheckCode.DUPLICATE_POSITION, not held,
            f"{'already holding' if held else 'no open position in'} {p.instrument.symbol}")
        group = p.instrument.correlation_group
        if group:
            n = sum(1 for pos in pf.positions if pos.correlation_group == group)
            add(CheckCode.CORRELATED_POSITIONS, n < L.max_correlated_positions,
                f"{n} open in group {group!r} (max {L.max_correlated_positions})")

        # Position sizing: fixed-fractional risk, capped by notional and exposure limits.
        qty = Decimal(0)
        if per_unit_risk > 0:
            qty = (pf.equity * L.max_risk_per_trade) / per_unit_risk
            caps = [pf.equity * L.max_position_notional / entry,
                    max(pf.equity * L.max_gross_exposure - pf.gross_exposure, Decimal(0)) / entry]
            if p.requested_quantity is not None:
                caps.append(p.requested_quantity)
            capped = min([qty, *caps])
            if capped < qty:
                add(CheckCode.SIZE_REDUCED, True, f"size capped from {qty:.8f} to {capped:.8f}")
            qty = capped
            lot = p.instrument.lot_size
            qty = (qty / lot).to_integral_value(rounding=ROUND_DOWN) * lot
        notional = qty * entry
        add(CheckCode.EXPOSURE, pf.gross_exposure + notional <= pf.equity * L.max_gross_exposure,
            f"gross exposure after trade {pf.gross_exposure + notional:.2f}")
        add(CheckCode.SIZE_TOO_SMALL, qty > 0 and notional >= p.instrument.min_notional,
            f"notional {notional:.2f} (min {p.instrument.min_notional})")

        approved = all(c.passed for c in checks)
        rr = None
        if p.take_profit is not None and per_unit_risk > 0:
            rr = (abs(p.take_profit - entry) / per_unit_risk).quantize(Decimal("0.01"))
        return RiskDecision(
            approved=approved,
            quantity=qty if approved else Decimal(0),
            notional=notional if approved else Decimal(0),
            risk_amount=(qty * per_unit_risk) if approved else Decimal(0),
            reward_risk=rr,
            checks=checks,
        )
