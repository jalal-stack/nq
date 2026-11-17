# Implementation Roadmap

Each phase ends with passing tests and updated docs. Real-money trading stays disabled in every
phase and requires a separate explicit decision by the owner plus a full security review.

Deployment target (no Docker anywhere): React/Vite frontend on Vercel; FastAPI on an Ubuntu VPS
behind Nginx (HTTPS) under systemd + Gunicorn/Uvicorn; PostgreSQL and Redis installed natively.

## Phase 0 — Foundation ✅
Domain types, settings with paper-only lock, market data abstraction + validation, indicators,
deterministic Risk Engine, PaperBroker, performance metrics, backtester, FastAPI, audit and
external integration register.

## Phase 0.5 — Deployment shape & first dashboard ✅
- API under `/api/v1` (health reports `mode: paper_only`, `live_execution_enabled: false`),
  CORS for the Vercel origin, WebSocket `/api/v1/ws/market`.
- Gunicorn config, hardened systemd unit, Nginx TLS/WebSocket config, PowerShell dev script,
  `docs/DEPLOYMENT.md`.
- Dashboard: health/paper badge, candle chart with EMA overlays and data-quality chips, live
  updates, backtest runner, risk-engine trade check.

## Phase 1 — Persistence
- Import the MVP into `legacy/mvp/` and port its `db.py` / `models.py` / `migrations/001_init.sql`
  as the baseline rather than designing a parallel schema (procedure: `docs/MVP_INTEGRATION.md`).
- SQLAlchemy 2 models: instruments, candles, proposals, risk decisions, approvals, orders,
  order events, fills, positions, closed trades, equity snapshots, agent runs, LLM usage.
- Alembic migrations against native PostgreSQL; SQLite for unit tests.
- Redis for OHLCV cache, provider rate limiting and WebSocket fan-out.
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
- Authentication for the API before it is exposed publicly with write endpoints.

## Phase 6 — Dashboard expansion
- Portfolio, equity curve, open orders/positions, proposal queue with risk check breakdown,
  agent run viewer, backtest/experiment comparison.

## Phase 7 — Strategy research
- Strategy library (EMA/RSI/ATR baseline, ORB, VWAP reversion, breakout), walk-forward and
  out-of-sample evaluation, parameter-stability reports. No strategy is called profitable
  without out-of-sample evidence across enough trades.
