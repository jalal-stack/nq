import { useEffect, useState } from "react";
import { BacktestPanel } from "./components/BacktestPanel";
import { MarketPanel, type MarketSelection } from "./components/MarketPanel";
import { RiskPanel } from "./components/RiskPanel";
import { Pill } from "./components/ui";
import { API_BASE, api, type AssetClass, type Health } from "./lib/api";

const assetClassFor = (s: MarketSelection): AssetClass =>
  s.provider === "ccxt" || s.provider === "synthetic" ? "crypto" : s.symbol.endsWith("=X") ? "forex" : "stock";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [selection, setSelection] = useState<MarketSelection>({ provider: "synthetic", symbol: "SYN-USD", timeframe: "1h" });
  const [lastPrice, setLastPrice] = useState<number | null>(null);

  useEffect(() => {
    api.health().then(setHealth, () => setHealthError(true));
  }, []);

  useEffect(() => {
    setLastPrice(null);
    api.ohlcv(selection.provider, selection.symbol, selection.timeframe, 10)
      .then((r) => setLastPrice(r.candles.at(-1)?.close ?? null), () => setLastPrice(null));
  }, [selection]);

  const assetClass = assetClassFor(selection);

  return (
    <div className="min-h-full">
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-sky-600 font-bold text-white">T</div>
            <div>
              <h1 className="text-base font-semibold text-slate-100">TradeMind AI</h1>
              <p className="text-xs text-slate-500">Quant research &amp; paper trading</p>
            </div>
          </div>
          <div className="flex items-center gap-2" data-testid="health">
            {health ? (
              <>
                <Pill tone="good">API online · v{health.version}</Pill>
                <Pill tone={health.live_execution_enabled ? "bad" : "warn"}>
                  {health.live_execution_enabled ? "LIVE EXECUTION ENABLED" : "PAPER ONLY · no real orders"}
                </Pill>
              </>
            ) : healthError ? (
              <Pill tone="bad">API unreachable at {API_BASE}</Pill>
            ) : (
              <Pill>Connecting…</Pill>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-4 px-4 py-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0 space-y-4">
          <MarketPanel selection={selection} onChange={setSelection} />
          <BacktestPanel selection={selection} assetClass={assetClass} />
        </div>
        <div className="min-w-0 space-y-4">
          <RiskPanel symbol={selection.symbol} assetClass={assetClass} startingEquity="5000" lastPrice={lastPrice} />
        </div>
      </main>

      <footer className="mx-auto max-w-7xl px-4 pb-6 text-xs text-slate-600">
        Research tool for personal use. Nothing shown here is financial advice or a promise of profit.
      </footer>
    </div>
  );
}
