# Architecture Audit

_Audit date: 2026-11-17. Repository: `jalal-stack/nq`, branch `main`, commit `28fe0c4`._

## 1. Findings: the expected MVP is not in this repository

The build brief describes an existing MVP (FastAPI, PostgreSQL, Redis, SQLAlchemy, Docker Compose,
CCXT, yfinance, an EMA/RSI/ATR strategy, paper-trading proposals, risk code, SQL migrations, pytest).
The audit found none of it:

| Check | Result |
|---|---|
| Repository tree | One file: `README.md` (Google AI Studio template banner) |
| Git history | One commit ("Initial commit"), full history fetched |
| Remote branches/tags | Only `main` |
| Source, config, dependencies | None |
| Database models / migrations | None |
| API endpoints | None |
| Tests | None to run |
| Security issues in existing code | None possible to assess (no code); no secrets committed |

Consequently nothing was deleted or overwritten, and no backup was required. The original
`README.md` is preserved and extended. If the MVP exists elsewhere, it should be pushed to a
branch here so it can be audited and merged into the module layout below; the new modules were
designed to absorb it (provider adapters, strategy protocol, risk engine interface).

Environment observed: Python 3.12.3, Node 24, no Docker daemon in the build sandbox.

### Re-audit (second brief, same day)

The second brief describes the MVP's layout (`backend/app/{main,config,db,models,schemas,seed,
market_data,strategy,risk,paper}.py`, `migrations/001_init.sql`, `GET /api/v1/health` returning
`paper_only` / `live_execution_enabled = false`, three passing risk tests). A fresh fetch of all
remote branches still shows no such files, so that code lives only on the owner's machine.
To stay compatible, this API now serves everything under `/api/v1` and `/api/v1/health` reports
`mode: "paper_only"` and `live_execution_enabled: false`. The new brief also forbids Docker:
nothing in this repository uses Docker, and deployment targets Vercel (frontend) and an Ubuntu
VPS with Nginx + systemd (backend). See `DEPLOYMENT.md`.

## 2. Implemented foundation (this change)

```
backend/trademind/
  config.py          settings; trading_mode is validated to be "paper" only
  domain.py          Instrument, Candle, Quote, enums (asset class, timeframe, order status)
  data/              provider ABC, CCXT/yfinance/synthetic adapters, validation & quality report
  indicators.py      EMA, RSI, MACD, ATR, VWAP, Bollinger, ADX (vectorized pandas)
  risk/engine.py     deterministic Risk Engine (final gate; LLMs cannot override)
  execution/paper.py PaperBroker: market/limit, fees, spread, slippage, partial fills, expiry, SL/TP
  performance/       net profit, win rate, PF, expectancy, Sharpe, Sortino, drawdown, exposure
  backtest/engine.py event-driven backtester sharing risk + execution with paper trading
  api/main.py        FastAPI under /api/v1: health, config, market OHLCV, risk/evaluate, backtest, ws/market
backend/tests/       26 pytest tests (offline, deterministic)
```

### Design decisions
- **Safety by construction.** No module imports a broker SDK, signs a transaction, or holds keys.
  `trading_mode` can only be `paper`; any other value fails at startup.
- **Deterministic risk gate.** `RiskEngine.evaluate` is a pure function of proposal, portfolio
  state and market context. It returns every check with pass/fail and detail, sizes positions by
  fixed-fractional risk with notional/exposure caps and lot rounding, and zeroes quantity on any
  failure. Agents will receive this result; they cannot change it.
- **Shared rules.** Backtests route through the same Risk Engine and PaperBroker as paper trading,
  so behaviour cannot drift between research and simulation.
- **No look-ahead.** Signals use closed bars; orders fill from the next bar.
- **Honest data labelling.** Providers declare `realtime`; yfinance is labelled delayed/unofficial.
  Every OHLCV response carries a `DataQualityReport` (duplicates, invalid rows, gaps, staleness).
- **Lightweight.** pandas/NumPy only; optional providers are lazily imported. Runs in well under 8 GB.

## 3. Gaps versus the brief

See `IMPLEMENTATION_ROADMAP.md` for sequencing. Not yet built: persistence (SQLAlchemy/Alembic,
PostgreSQL, Redis), the 12 LLM agents and orchestrator, the LLM provider
abstraction, news/fundamental/sentiment data sources, user approval workflow, read-only on-chain
adapters, and the portfolio/proposal/agent views of the dashboard.

## 4. External tools

Evaluated in `EXTERNAL_INTEGRATIONS.md`. Nothing external was installed or executed.
