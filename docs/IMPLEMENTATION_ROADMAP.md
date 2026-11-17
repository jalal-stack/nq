# Implementation Roadmap

Each phase ends with passing tests and updated docs. Real-money trading stays disabled in every phase.

## Phase 0 — Foundation ✅ (this change)
Domain types, settings with paper-only lock, market data abstraction + validation, indicators,
deterministic Risk Engine, PaperBroker, performance metrics, backtester, FastAPI, 24 tests,
audit and external integration register.

## Phase 1 — Persistence & infrastructure
- SQLAlchemy 2 models: instruments, candles, proposals, risk decisions, approvals, orders,
  order events, fills, positions, closed trades, equity snapshots, agent runs, LLM usage.
- Alembic migrations; PostgreSQL in Docker Compose, SQLite for tests.
- Redis for OHLCV cache and provider rate limiting.
- Docker Compose (api, db, redis, web) with health checks; Windows 10 / WSL 2 notes.
- Structured JSON logging with request and run IDs.

## Phase 2 — Market data hardening
- CCXT and yfinance adapters with retries, rate limits and contract tests against recorded fixtures.
- Instrument metadata (lot/tick size, min notional), bid/ask & spread capture.
- Exchange calendars for equity sessions/holidays (replace the simplified UTC window).

## Phase 3 — Agent framework
- `Agent` interface: typed Pydantic input/output, versioned prompt files, timeout, bounded retries,
  run log with inputs hash for reproducibility, token/cost accounting.
- LLM provider abstraction (Anthropic Claude, optional Google Gemini) with JSON-schema
  structured output and strict validation; a deterministic fake provider for tests.
- Orchestrator as a fixed DAG (no recursion, max-steps guard):
  Scanner → Technical → Fundamental → News → Sentiment → Bull/Bear → Strategy → Portfolio
  → **Risk Engine** → User approval → Paper execution → Performance.
- Deterministic agents first (Scanner, Technical, Portfolio, Risk, Execution, Performance);
  LLM agents interpret evidence and must cite the shared data snapshot.

## Phase 4 — Research data sources
- Fundamentals, economic calendar, news (with dedupe and source/time), sentiment
  (fear & greed, funding rates). Unavailable fields are returned as missing, never invented.
- Read-only on-chain adapters per `EXTERNAL_INTEGRATIONS.md` (DexScreener, GoPlus, Jupiter quote,
  explorer APIs). No signing, no private keys.

## Phase 5 — Approval workflow & paper trading service
- Proposal → risk decision → user approve/reject → PaperBroker, with full audit trail.
- Live mark-to-market loop on polled bars; daily-loss and drawdown halts.

## Phase 6 — Dashboard (React + TypeScript + Vite + Tailwind)
- Portfolio, equity curve, open orders/positions, proposal queue with risk check breakdown,
  agent run viewer, backtest/experiment comparison, data-quality indicators, interactive charts.

## Phase 7 — Strategy research
- Strategy library (EMA/RSI/ATR baseline, ORB, VWAP reversion, breakout), walk-forward and
  out-of-sample evaluation, parameter-stability reports. No strategy is called profitable
  without out-of-sample evidence across enough trades.
