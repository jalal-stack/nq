import { useState } from "react";
import { api, type AssetClass, type BacktestResult } from "../lib/api";
import { checkLabel, fmtNum, fmtPct, fmtUsd } from "../lib/format";
import type { MarketSelection } from "./MarketPanel";
import { Card, ErrorNote, Pill, Stat } from "./ui";

export function BacktestPanel({ selection, assetClass }: { selection: MarketSelection; assetClass: AssetClass }) {
  const [bars, setBars] = useState(2000);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      setResult(await api.backtest({ ...selection, bars, asset_class: assetClass }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const r = result?.report;
  const tone = (v: number | null | undefined) => (v == null ? "neutral" : v > 0 ? "good" : v < 0 ? "bad" : "neutral");

  return (
    <Card title="Backtest · EMA/RSI/ATR baseline">
      <div className="mb-3 flex items-end gap-2">
        <div className="flex-1">
          <label className="label" htmlFor="bars">Bars</label>
          <input id="bars" type="number" min={100} max={10000} step={100} className="input" value={bars}
            onChange={(e) => setBars(Number(e.target.value))} />
        </div>
        <button className="btn" onClick={run} disabled={running}>{running ? "Running…" : "Run backtest"}</button>
      </div>
      <p className="mb-3 text-xs text-slate-500">
        {selection.provider} · {selection.symbol} · {selection.timeframe}. Uses the same risk engine and paper broker as paper trading.
      </p>
      <ErrorNote error={error} />
      {result && r && (
        <div className="space-y-3" data-testid="backtest-result">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <Stat label="Net profit" value={fmtUsd(r.net_profit)} tone={tone(r.net_profit)} />
            <Stat label="Trades" value={String(r.trades)} />
            <Stat label="Win rate" value={fmtPct(r.win_rate)} />
            <Stat label="Profit factor" value={fmtNum(r.profit_factor)} />
            <Stat label="Max drawdown" value={fmtPct(r.max_drawdown)} tone={r.max_drawdown > 0.1 ? "bad" : "neutral"} />
            <Stat label="Expectancy" value={fmtUsd(r.expectancy)} tone={tone(r.expectancy)} />
            <Stat label="Sharpe" value={fmtNum(r.sharpe)} />
            <Stat label="Sortino" value={fmtNum(r.sortino)} />
            <Stat label="Fees paid" value={fmtUsd(r.total_fees)} />
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <Pill>{result.signals} signals</Pill>
            {Object.entries(result.risk_rejections).map(([code, n]) => (
              <Pill key={code} tone="warn">{checkLabel(code)}: {n} rejected</Pill>
            ))}
          </div>
          <p className="rounded-md border border-amber-800/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-200/90">
            {r.sample_warning ? `${r.sample_warning}. ` : ""}A backtest is not evidence of future profit
            {selection.provider === "synthetic" ? "; this one ran on random synthetic data" : ""}.
          </p>
        </div>
      )}
    </Card>
  );
}
