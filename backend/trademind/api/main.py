"""HTTP + WebSocket API under /api/v1. Exposes research, risk and paper-trading
functions; no live-trading routes exist."""

from __future__ import annotations

import asyncio
import math

from fastapi import APIRouter, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from trademind import __version__
from trademind.backtest.engine import BacktestResult, EmaRsiAtrStrategy, run_backtest
from trademind.config import get_settings
from trademind.data.base import MarketDataProvider, ProviderError
from trademind.data.providers import SyntheticProvider
from trademind.data.validation import DataQualityReport, assess
from trademind.domain import AssetClass, Instrument, Timeframe
from trademind.indicators import compute_all
from trademind.risk.engine import (
    MarketContext, PortfolioState, RiskDecision, RiskEngine, RiskLimits, TradeProposal,
)

API_PREFIX = "/api/v1"

app = FastAPI(title="TradeMind AI", version=__version__, docs_url="/docs", openapi_url="/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
router = APIRouter(prefix=API_PREFIX)


def _provider(name: str) -> MarketDataProvider:
    if name == "synthetic":
        return SyntheticProvider()
    try:
        from trademind.data.providers import CCXTProvider, YFinanceProvider
        return {"ccxt": CCXTProvider, "yfinance": YFinanceProvider}[name]()
    except KeyError:
        raise HTTPException(404, f"unknown provider {name!r}")
    except ProviderError as e:
        raise HTTPException(503, str(e))


@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "version": __version__, "mode": "paper_only",
            "trading_mode": s.trading_mode, "live_execution_enabled": False}


@router.get("/config")
def config() -> dict:
    s = get_settings()
    return {"base_currency": s.base_currency, "starting_equity": str(s.starting_equity),
            "trading_mode": s.trading_mode, "risk_limits": RiskLimits.from_settings(s).model_dump(mode="json")}


class OhlcvResponse(BaseModel):
    symbol: str
    provider: str
    timeframe: Timeframe
    realtime: bool
    quality: DataQualityReport
    candles: list[dict]


def _records(df) -> list[dict]:
    out = []
    for ts, row in df.iterrows():
        rec = {"ts": ts.isoformat()}
        rec.update({k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()})
        out.append(rec)
    return out


def _load_ohlcv(provider: str, symbol: str, timeframe: Timeframe, limit: int,
                indicators: bool, continuous: bool) -> OhlcvResponse:
    p = _provider(provider)
    try:
        raw = p.fetch_ohlcv(symbol, timeframe, limit=limit)
    except ProviderError as e:
        raise HTTPException(502, str(e))
    df, report = assess(raw, timeframe, continuous=continuous,
                        max_age_seconds=get_settings().max_data_age_seconds)
    if indicators:
        df = compute_all(df)
    return OhlcvResponse(symbol=symbol, provider=p.name, timeframe=timeframe, realtime=p.realtime,
                         quality=report, candles=_records(df))


@router.get("/market/{provider}/ohlcv", response_model=OhlcvResponse)
def ohlcv(provider: str, symbol: str, timeframe: Timeframe = Timeframe.H1,
          limit: int = Query(300, ge=10, le=2000), indicators: bool = False,
          continuous: bool = True) -> OhlcvResponse:
    return _load_ohlcv(provider, symbol, timeframe, limit, indicators, continuous)


class RiskRequest(BaseModel):
    proposal: TradeProposal
    portfolio: PortfolioState
    context: MarketContext


@router.post("/risk/evaluate", response_model=RiskDecision)
def risk_evaluate(req: RiskRequest) -> RiskDecision:
    return RiskEngine(RiskLimits.from_settings(get_settings())).evaluate(req.proposal, req.portfolio, req.context)


class BacktestRequest(BaseModel):
    symbol: str = "SYN-USD"
    asset_class: AssetClass = AssetClass.CRYPTO
    provider: str = "synthetic"
    timeframe: Timeframe = Timeframe.H1
    bars: int = Field(2000, ge=100, le=10000)


@router.post("/backtest", response_model=BacktestResult)
def backtest(req: BacktestRequest) -> BacktestResult:
    p = _provider(req.provider)
    df, report = assess(p.fetch_ohlcv(req.symbol, req.timeframe, limit=req.bars), req.timeframe)
    if report.rows < 100:
        raise HTTPException(422, "not enough clean data to backtest")
    periods = 365 * 86400 / req.timeframe.seconds
    return run_backtest(df, Instrument(symbol=req.symbol, asset_class=req.asset_class),
                        EmaRsiAtrStrategy(), starting_cash=float(get_settings().starting_equity),
                        periods_per_year=periods)


@router.websocket("/ws/market")
async def ws_market(ws: WebSocket, provider: str = "synthetic", symbol: str = "SYN-USD",
                    timeframe: Timeframe = Timeframe.M1) -> None:
    """Sends a `snapshot` with recent candles, then the latest candle as `update` every
    `ws_push_interval_seconds` (polling the provider; no exchange stream is opened)."""
    # CORS does not cover WebSockets, so browser origins are checked here.
    origin = ws.headers.get("origin")
    if origin is not None and origin not in get_settings().cors_origin_list:
        await ws.close(code=1008)
        return
    await ws.accept()
    interval = get_settings().ws_push_interval_seconds
    try:
        snap = await run_in_threadpool(_load_ohlcv, provider, symbol, timeframe, 200, False, True)
        await ws.send_json({"type": "snapshot", **snap.model_dump(mode="json")})
        while True:
            await asyncio.sleep(interval)
            latest = await run_in_threadpool(_load_ohlcv, provider, symbol, timeframe, 10, False, True)
            await ws.send_json({"type": "update", "symbol": symbol, "candle": latest.candles[-1],
                                "quality": latest.quality.model_dump(mode="json")})
    except HTTPException as e:
        await ws.send_json({"type": "error", "status": e.status_code, "detail": e.detail})
        await ws.close(code=1011)
    except WebSocketDisconnect:
        pass


app.include_router(router)
