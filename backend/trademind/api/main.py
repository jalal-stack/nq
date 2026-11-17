"""HTTP API. Exposes research, risk and paper-trading functions; no live-trading routes exist."""

from __future__ import annotations

import math

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from trademind import __version__
from trademind.backtest.engine import BacktestResult, EmaRsiAtrStrategy, run_backtest
from trademind.config import get_settings
from trademind.data.base import ProviderError
from trademind.data.providers import SyntheticProvider
from trademind.data.validation import DataQualityReport, assess
from trademind.domain import AssetClass, Instrument, Timeframe
from trademind.indicators import compute_all
from trademind.risk.engine import (
    MarketContext, PortfolioState, RiskDecision, RiskEngine, RiskLimits, TradeProposal,
)

app = FastAPI(title="TradeMind AI", version=__version__)


def _provider(name: str):
    if name == "synthetic":
        return SyntheticProvider()
    try:
        from trademind.data.providers import CCXTProvider, YFinanceProvider
        return {"ccxt": CCXTProvider, "yfinance": YFinanceProvider}[name]()
    except KeyError:
        raise HTTPException(404, f"unknown provider {name!r}")
    except ProviderError as e:
        raise HTTPException(503, str(e))


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "version": __version__, "trading_mode": s.trading_mode,
            "live_trading_enabled": False}


@app.get("/config")
def config() -> dict:
    s = get_settings()
    return {"base_currency": s.base_currency, "starting_equity": str(s.starting_equity),
            "trading_mode": s.trading_mode, "risk_limits": RiskLimits.from_settings(s).model_dump(mode="json")}


class OhlcvResponse(BaseModel):
    symbol: str
    provider: str
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


@app.get("/market/{provider}/ohlcv", response_model=OhlcvResponse)
def ohlcv(provider: str, symbol: str, timeframe: Timeframe = Timeframe.H1,
          limit: int = Query(300, ge=10, le=2000), indicators: bool = False,
          continuous: bool = True) -> OhlcvResponse:
    p = _provider(provider)
    try:
        raw = p.fetch_ohlcv(symbol, timeframe, limit=limit)
    except ProviderError as e:
        raise HTTPException(502, str(e))
    df, report = assess(raw, timeframe, continuous=continuous,
                        max_age_seconds=get_settings().max_data_age_seconds)
    if indicators:
        df = compute_all(df)
    return OhlcvResponse(symbol=symbol, provider=p.name, realtime=p.realtime, quality=report,
                         candles=_records(df))


class RiskRequest(BaseModel):
    proposal: TradeProposal
    portfolio: PortfolioState
    context: MarketContext


@app.post("/risk/evaluate", response_model=RiskDecision)
def risk_evaluate(req: RiskRequest) -> RiskDecision:
    return RiskEngine(RiskLimits.from_settings(get_settings())).evaluate(req.proposal, req.portfolio, req.context)


class BacktestRequest(BaseModel):
    symbol: str = "SYN-USD"
    asset_class: AssetClass = AssetClass.CRYPTO
    provider: str = "synthetic"
    timeframe: Timeframe = Timeframe.H1
    bars: int = 2000


@app.post("/backtest", response_model=BacktestResult)
def backtest(req: BacktestRequest) -> BacktestResult:
    p = _provider(req.provider)
    df, report = assess(p.fetch_ohlcv(req.symbol, req.timeframe, limit=req.bars), req.timeframe)
    if report.rows < 100:
        raise HTTPException(422, "not enough clean data to backtest")
    periods = 365 * 86400 / req.timeframe.seconds
    return run_backtest(df, Instrument(symbol=req.symbol, asset_class=req.asset_class),
                        EmaRsiAtrStrategy(), starting_cash=float(get_settings().starting_equity),
                        periods_per_year=periods)
