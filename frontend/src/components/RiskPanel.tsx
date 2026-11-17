import { useState } from "react";
import { api, type AssetClass, type RiskDecision } from "../lib/api";
import { checkLabel, fmtNum, fmtUsd } from "../lib/format";
import { Card, ErrorNote, Pill } from "./ui";

interface Form {
  side: "buy" | "sell";
  entry: string;
  stop: string;
  target: string;
  atr: string;
  equity: string;
}

export function RiskPanel({ symbol, assetClass, startingEquity, lastPrice }: {
  symbol: string;
  assetClass: AssetClass;
  startingEquity: string;
  lastPrice: number | null;
}) {
  const [f, setF] = useState<Form>({ side: "buy", entry: "", stop: "", target: "", atr: "", equity: startingEquity });
  const [decision, setDecision] = useState<RiskDecision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF({ ...f, [k]: e.target.value });

  const evaluate = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const now = new Date().toISOString();
    try {
      setDecision(
        await api.evaluateRisk({
          proposal: {
            instrument: { symbol, asset_class: assetClass, ...(assetClass === "stock" ? { lot_size: "1" } : {}) },
            side: f.side,
            entry_price: f.entry,
            stop_loss: f.stop,
            ...(f.target ? { take_profit: f.target } : {}),
            strategy: "manual",
          },
          portfolio: { equity: f.equity, peak_equity: f.equity, day_start_equity: f.equity },
          context: { as_of: now, last_data_ts: now, ...(f.atr ? { atr: f.atr } : {}) },
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setDecision(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Risk engine · trade check">
      <form onSubmit={evaluate} className="grid grid-cols-2 gap-2">
        <div>
          <label className="label" htmlFor="side">Side</label>
          <select id="side" className="input" value={f.side} onChange={set("side")}>
            <option value="buy">Buy (long)</option>
            <option value="sell">Sell (short)</option>
          </select>
        </div>
        <div>
          <label className="label" htmlFor="equity">Equity (USD)</label>
          <input id="equity" className="input" inputMode="decimal" value={f.equity} onChange={set("equity")} />
        </div>
        <div>
          <label className="label" htmlFor="entry">Entry</label>
          <div className="flex gap-1">
            <input id="entry" className="input" inputMode="decimal" value={f.entry} onChange={set("entry")} required />
            {lastPrice !== null && (
              <button type="button" className="rounded-md border border-slate-700 px-2 text-xs text-slate-400 hover:text-slate-200"
                onClick={() => setF({ ...f, entry: lastPrice.toFixed(2) })} title="Use last price">Last</button>
            )}
          </div>
        </div>
        <div>
          <label className="label" htmlFor="stop">Stop loss</label>
          <input id="stop" className="input" inputMode="decimal" value={f.stop} onChange={set("stop")} required />
        </div>
        <div>
          <label className="label" htmlFor="target">Take profit</label>
          <input id="target" className="input" inputMode="decimal" value={f.target} onChange={set("target")} placeholder="optional" />
        </div>
        <div>
          <label className="label" htmlFor="atr">ATR</label>
          <input id="atr" className="input" inputMode="decimal" value={f.atr} onChange={set("atr")} placeholder="optional" />
        </div>
        <button className="btn col-span-2 mt-1" disabled={busy}>{busy ? "Checking…" : "Check trade"}</button>
      </form>

      <div className="mt-3 space-y-3">
        <ErrorNote error={error} />
        {decision && (
          <div data-testid="risk-decision">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Pill tone={decision.approved ? "good" : "bad"}>{decision.approved ? "APPROVED" : "REJECTED"}</Pill>
              {decision.approved && (
                <span className="text-sm text-slate-300">
                  Size <span className="font-mono">{fmtNum(decision.quantity, 6)}</span> · notional {fmtUsd(decision.notional)} · risk {fmtUsd(decision.risk_amount)}
                  {decision.reward_risk && <> · R:R {decision.reward_risk}</>}
                </span>
              )}
            </div>
            <ul className="divide-y divide-slate-800 rounded-md border border-slate-800 text-sm">
              {decision.checks.map((c, i) => (
                <li key={i} className="flex items-start gap-2 px-3 py-1.5">
                  <span className={c.passed ? "text-emerald-400" : "text-rose-400"}>{c.passed ? "✓" : "✕"}</span>
                  <span className="w-36 shrink-0 text-slate-300">{checkLabel(c.code)}</span>
                  <span className="min-w-0 font-mono text-xs text-slate-500 [overflow-wrap:anywhere]">{c.detail}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
