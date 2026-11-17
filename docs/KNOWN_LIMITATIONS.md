# Known Limitations

## Scope
- Paper trading only. There is intentionally no live broker, exchange or blockchain execution code.
- The existing MVP described in the brief was not found in this repository (see `ARCHITECTURE_AUDIT.md`).
- Not yet implemented: database persistence, Docker Compose, LLM agents/orchestrator, news,
  fundamentals, sentiment, on-chain adapters, approval workflow, dashboard.

## Market data
- yfinance is an unofficial Yahoo Finance client: delayed, best-effort, limited intraday history,
  subject to Yahoo's terms. It is not institutional or real-time data.
- CCXT adapters use public endpoints only; exchange availability varies by country.
- CCXT and yfinance adapters have no network tests yet; tests use the synthetic provider.
- Gap detection for non-continuous markets ignores every overnight/weekend gap and does not use
  exchange calendars, so missing bars at session boundaries are not detected.

## Risk engine
- US equity session is a fixed 13:30–21:00 UTC window (DST and holidays not modelled; the window
  is permissive during EST). Forex weekend closure is approximate.
- Correlation is by user-assigned `correlation_group`, not measured return correlation.
- Exposure is gross notional, unlevered; no margin model.

## Paper execution & backtesting
- Uses floats internally (risk sizing uses Decimal); rounding differences are sub-cent.
- Bar-based fills: intrabar path is unknown, so when stop and target are both touched in one bar
  the stop is assumed first. Stop/target exits are not capped by bar volume.
- Spread and slippage are fixed bps, not measured from order books.
- Single-symbol backtester; no portfolio-level multi-asset backtest yet.

## Performance metrics
- Sharpe/Sortino use per-bar equity returns annualized by the caller-supplied periods per year,
  with zero risk-free rate.
- Fewer than 30 trades triggers a `sample_warning`; even above that, results on synthetic data or a
  single period are not evidence of an edge. Synthetic random-walk backtests can show profit purely
  by chance.
