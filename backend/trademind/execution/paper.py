"""Paper execution engine. Simulation only: there is no code path that reaches a
broker, exchange or blockchain.

Fill model (applied per bar, orders are never filled on the bar they were submitted on):
- market orders fill at the next bar's open, plus half the spread and slippage against the trader;
- limit orders fill at the limit (or a better open) when the bar trades through it;
- fill size is capped at `max_participation` of the bar's volume, leaving the rest working;
- orders past `expires_at` expire; remaining quantity is cancelled.
- protective stop / take-profit are checked per bar; if both are touched in one bar
  the stop is assumed to fill first (conservative).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field

from trademind.domain import Candle, OrderStatus, OrderType, Side


class CostModel(BaseModel):
    fee_bps: float = 10.0
    spread_bps: float = 2.0
    slippage_bps: float = 2.0
    max_participation: float = Field(default=0.1, gt=0, le=1)


class OrderEvent(BaseModel):
    ts: datetime
    status: OrderStatus
    detail: str = ""
    fill_qty: float = 0.0
    fill_price: float | None = None
    fee: float = 0.0


class Order(BaseModel):
    id: int
    symbol: str
    side: Side
    type: OrderType
    quantity: float = Field(gt=0)
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    created_at: datetime
    expires_at: datetime | None = None
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    fees: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    events: list[OrderEvent] = Field(default_factory=list)
    reduce_only: bool = False
    tag: str = ""

    @property
    def remaining(self) -> float:
        return self.quantity - self.filled_qty

    @property
    def is_open(self) -> bool:
        return self.status in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED)


class ClosedTrade(BaseModel):
    symbol: str
    side: Side  # side of the opening position
    quantity: float
    entry_price: float
    exit_price: float
    entry_ts: datetime
    exit_ts: datetime
    fees: float
    pnl: float  # net of fees attributable to this round trip
    exit_reason: str
    strategy: str = ""


@dataclass
class Position:
    symbol: str
    quantity: float  # signed: >0 long, <0 short
    avg_price: float
    opened_at: datetime
    entry_fees: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    strategy: str = ""
    mark: float = 0.0

    @property
    def side(self) -> Side:
        return Side.BUY if self.quantity > 0 else Side.SELL


@dataclass
class PaperBroker:
    starting_cash: float = 5000.0
    costs: CostModel = field(default_factory=CostModel)
    cash: float = field(init=False)
    orders: dict[int, Order] = field(default_factory=dict, init=False)
    positions: dict[str, Position] = field(default_factory=dict, init=False)
    trades: list[ClosedTrade] = field(default_factory=list, init=False)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list, init=False)
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1), init=False)

    def __post_init__(self) -> None:
        self.cash = self.starting_cash

    # ---- account -------------------------------------------------------------------
    @property
    def equity(self) -> float:
        return self.cash + sum(p.quantity * p.mark for p in self.positions.values())

    @property
    def gross_exposure(self) -> float:
        return sum(abs(p.quantity * p.mark) for p in self.positions.values())

    # ---- orders --------------------------------------------------------------------
    def submit(
        self,
        symbol: str,
        side: Side,
        quantity: float,
        ts: datetime,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        expires_at: datetime | None = None,
        tag: str = "",
        reduce_only: bool = False,
    ) -> Order:
        order = Order(
            id=next(self._ids), symbol=symbol, side=side, type=order_type, quantity=quantity,
            limit_price=limit_price, stop_loss=stop_loss, take_profit=take_profit,
            created_at=ts, expires_at=expires_at, tag=tag, reduce_only=reduce_only,
        )
        self.orders[order.id] = order
        reason = self._validate(order)
        if reason:
            self._event(order, ts, OrderStatus.REJECTED, reason)
        else:
            self._event(order, ts, OrderStatus.PENDING, "accepted")
        return order

    def cancel(self, order_id: int, ts: datetime) -> Order:
        order = self.orders[order_id]
        if order.is_open:
            self._event(order, ts, OrderStatus.CANCELLED, "cancelled by user")
        return order

    def _validate(self, o: Order) -> str | None:
        if o.type == OrderType.LIMIT and (o.limit_price is None or o.limit_price <= 0):
            return "limit order requires a positive limit_price"
        ref = o.limit_price
        if o.side == Side.BUY and o.stop_loss is not None and ref and o.stop_loss >= ref:
            return "stop_loss must be below limit price for buys"
        if o.side == Side.SELL and o.stop_loss is not None and ref and o.stop_loss <= ref:
            return "stop_loss must be above limit price for sells"
        return None

    def _event(self, o: Order, ts: datetime, status: OrderStatus, detail: str = "",
               qty: float = 0.0, price: float | None = None, fee: float = 0.0) -> None:
        o.status = status
        o.events.append(OrderEvent(ts=ts, status=status, detail=detail, fill_qty=qty, fill_price=price, fee=fee))

    # ---- simulation ----------------------------------------------------------------
    def on_bar(self, symbol: str, bar: Candle) -> None:
        for o in list(self.orders.values()):
            if o.symbol != symbol or not o.is_open or o.created_at >= bar.ts:
                continue
            if o.expires_at is not None and bar.ts >= o.expires_at:
                self._event(o, bar.ts, OrderStatus.EXPIRED, f"expired with {o.remaining} unfilled")
                continue
            self._try_fill(o, bar)
        self._check_exits(symbol, bar)
        if symbol in self.positions:
            self.positions[symbol].mark = bar.close
        self.equity_curve.append((bar.ts, self.equity))

    def _fill_price(self, side: Side, base: float, apply_spread: bool = True) -> float:
        bps = self.costs.slippage_bps + (self.costs.spread_bps / 2 if apply_spread else 0)
        adj = base * bps / 10_000
        return base + adj if side == Side.BUY else base - adj

    def _try_fill(self, o: Order, bar: Candle) -> None:
        if o.type == OrderType.MARKET:
            price = self._fill_price(o.side, bar.open)
        else:
            lp = o.limit_price
            assert lp is not None
            if o.side == Side.BUY and bar.low <= lp:
                price = min(lp, bar.open)
            elif o.side == Side.SELL and bar.high >= lp:
                price = max(lp, bar.open)
            else:
                return
        qty = o.remaining
        if o.reduce_only:
            pos = self.positions.get(o.symbol)
            qty = min(qty, abs(pos.quantity)) if pos else 0.0
            if qty <= 0:
                self._event(o, bar.ts, OrderStatus.CANCELLED, "reduce-only with no position")
                return
        cap = bar.volume * self.costs.max_participation
        if cap <= 0:
            return
        qty = min(qty, cap)
        notional = qty * price
        fee = notional * self.costs.fee_bps / 10_000
        if not o.reduce_only and not self._affordable(o, notional + fee):
            self._event(o, bar.ts, OrderStatus.REJECTED, "insufficient buying power")
            return
        prev = o.filled_qty
        o.filled_qty += qty
        o.avg_fill_price = ((o.avg_fill_price or 0) * prev + price * qty) / o.filled_qty
        o.fees += fee
        status = OrderStatus.FILLED if o.remaining <= 1e-12 else OrderStatus.PARTIALLY_FILLED
        self._event(o, bar.ts, status, "fill", qty, price, fee)
        self._apply_fill(o, qty, price, fee, bar.ts, reason=o.tag or "order")

    def _affordable(self, o: Order, cost: float) -> bool:
        # Unlevered account: gross exposure after the fill may not exceed equity.
        pos = self.positions.get(o.symbol)
        signed = cost if o.side == Side.BUY else -cost
        reducing = pos is not None and (pos.quantity > 0) != (signed > 0)
        return reducing or self.gross_exposure + cost <= self.equity

    def _apply_fill(self, o: Order, qty: float, price: float, fee: float, ts: datetime, reason: str) -> None:
        signed = qty if o.side == Side.BUY else -qty
        self.cash -= signed * price + fee
        pos = self.positions.get(o.symbol)
        if pos is None:
            self.positions[o.symbol] = Position(
                symbol=o.symbol, quantity=signed, avg_price=price, opened_at=ts, entry_fees=fee,
                stop_loss=o.stop_loss, take_profit=o.take_profit, strategy=o.tag, mark=price)
            return
        if (pos.quantity > 0) == (signed > 0):
            total = pos.quantity + signed
            pos.avg_price = (pos.avg_price * pos.quantity + price * signed) / total
            pos.quantity = total
            pos.entry_fees += fee
            return
        closing = min(abs(signed), abs(pos.quantity))
        frac = closing / abs(pos.quantity)
        entry_fee_part = pos.entry_fees * frac
        direction = 1 if pos.quantity > 0 else -1
        gross = (price - pos.avg_price) * closing * direction
        exit_fee_part = fee * closing / qty
        self.trades.append(ClosedTrade(
            symbol=o.symbol, side=pos.side, quantity=closing, entry_price=pos.avg_price, exit_price=price,
            entry_ts=pos.opened_at, exit_ts=ts, fees=entry_fee_part + exit_fee_part,
            pnl=gross - entry_fee_part - exit_fee_part, exit_reason=reason, strategy=pos.strategy))
        pos.entry_fees -= entry_fee_part
        pos.quantity += direction * -closing
        leftover = abs(signed) - closing
        if abs(pos.quantity) <= 1e-12:
            del self.positions[o.symbol]
            if leftover > 1e-12:  # position flipped
                self.positions[o.symbol] = Position(
                    symbol=o.symbol, quantity=leftover if signed > 0 else -leftover, avg_price=price,
                    opened_at=ts, entry_fees=fee - exit_fee_part, strategy=o.tag, mark=price)

    def _check_exits(self, symbol: str, bar: Candle) -> None:
        pos = self.positions.get(symbol)
        if pos is None or pos.opened_at > bar.ts:
            return
        long = pos.quantity > 0
        exit_side = Side.SELL if long else Side.BUY
        price = reason = None
        if pos.stop_loss is not None and (bar.low <= pos.stop_loss if long else bar.high >= pos.stop_loss):
            gap_through = bar.open < pos.stop_loss if long else bar.open > pos.stop_loss
            price, reason = (bar.open if gap_through else pos.stop_loss), "stop_loss"
        elif pos.take_profit is not None and (bar.high >= pos.take_profit if long else bar.low <= pos.take_profit):
            gap_through = bar.open > pos.take_profit if long else bar.open < pos.take_profit
            price, reason = (bar.open if gap_through else pos.take_profit), "take_profit"
        if price is None:
            return
        # Stops execute as market orders (spread + slippage); take-profits as resting limits.
        fill = self._fill_price(exit_side, price) if reason == "stop_loss" else price
        qty = abs(pos.quantity)
        o = Order(id=next(self._ids), symbol=symbol, side=exit_side, type=OrderType.MARKET, quantity=qty,
                  created_at=bar.ts, reduce_only=True, tag=reason)
        self.orders[o.id] = o
        fee = qty * fill * self.costs.fee_bps / 10_000
        o.filled_qty, o.avg_fill_price, o.fees = qty, fill, fee
        self._event(o, bar.ts, OrderStatus.FILLED, reason, qty, fill, fee)
        self._apply_fill(o, qty, fill, fee, bar.ts, reason=reason)
