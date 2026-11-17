import { useCallback, useEffect, useState } from "react";
import { api, wsUrl, type CandleRow, type DataQuality, type OhlcvResponse, type Provider, type Timeframe } from "../lib/api";
import { fmtAge, fmtUsd } from "../lib/format";
import { CandleChart } from "./CandleChart";
import { Card, ErrorNote, Pill } from "./ui";

export interface MarketSelection {
  provider: Provider;
  symbol: string;
  timeframe: Timeframe;
}

const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h", "4h", "1d"];

export function MarketPanel({ selection, onChange }: {
  selection: MarketSelection;
  onChange: (s: MarketSelection) => void;
}) {
  const [draft, setDraft] = useState(selection);
  const [data, setData] = useState<OhlcvResponse | null>(null);
  const [quality, setQuality] = useState<DataQuality | null>(null);
  const [liveCandle, setLiveCandle] = useState<CandleRow | null>(null);
  const [liveOn, setLiveOn] = useState(false);
  const [liveState, setLiveState] = useState<"off" | "connecting" | "open" | "closed">("off");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (s: MarketSelection) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.ohlcv(s.provider, s.symbol, s.timeframe);
      setData(res);
      setQuality(res.quality);
      setLiveCandle(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(selection);
  }, [selection, load]);

  useEffect(() => {
    if (!liveOn) {
      setLiveState("off");
      return;
    }
    setLiveState("connecting");
    const ws = new WebSocket(wsUrl("/ws/market", { ...selection }));
    ws.onopen = () => setLiveState("open");
    ws.onclose = () => setLiveState("closed");
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "update") {
        setLiveCandle(msg.candle);
        setQuality(msg.quality);
      } else if (msg.type === "error") {
        setError(`Live feed: ${msg.detail}`);
      }
    };
    return () => ws.close();
  }, [liveOn, selection]);

  const last = liveCandle ?? data?.candles.at(-1) ?? null;

  return (
    <Card
      title="Market"
      actions={
        <div className="flex items-center gap-2">
          {data && <Pill tone={data.realtime ? "good" : "warn"}>{data.realtime ? "real-time source" : "delayed / simulated"}</Pill>}
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-400">
            <input type="checkbox" checked={liveOn} onChange={(e) => setLiveOn(e.target.checked)} className="accent-sky-500" />
            Live <span className="text-slate-500">({liveState})</span>
          </label>
        </div>
      }
    >
      <form
        className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-[140px_1fr_110px_auto]"
        onSubmit={(e) => {
          e.preventDefault();
          onChange({ ...draft, symbol: draft.symbol.trim() });
        }}
      >
        <select className="input" value={draft.provider} onChange={(e) => setDraft({ ...draft, provider: e.target.value as Provider })} aria-label="Provider">
          <option value="synthetic">Synthetic</option>
          <option value="ccxt">CCXT (crypto)</option>
          <option value="yfinance">yfinance (stocks/FX)</option>
        </select>
        <input className="input" value={draft.symbol} onChange={(e) => setDraft({ ...draft, symbol: e.target.value })} aria-label="Symbol" placeholder="BTC/USDT, AAPL, EURUSD=X" />
        <select className="input" value={draft.timeframe} onChange={(e) => setDraft({ ...draft, timeframe: e.target.value as Timeframe })} aria-label="Timeframe">
          {TIMEFRAMES.map((t) => <option key={t}>{t}</option>)}
        </select>
        <button className="btn" disabled={loading || !draft.symbol.trim()}>{loading ? "Loading…" : "Load"}</button>
      </form>

      <ErrorNote error={error} />

      <div className="mb-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="text-lg font-semibold text-slate-100">{selection.symbol}</span>
        <span className="font-mono text-lg tabular-nums">{last ? fmtUsd(last.close) : "—"}</span>
        <span className="text-xs text-slate-500">
          <span className="text-sky-400">━ EMA 20</span> <span className="ml-2 text-amber-400">━ EMA 50</span>
        </span>
      </div>

      <CandleChart candles={data?.candles ?? []} live={liveCandle} />

      {quality && (
        <div className="mt-3 flex flex-wrap gap-2 text-xs" data-testid="data-quality">
          <Pill>{quality.rows} candles</Pill>
          <Pill tone={quality.missing_candles ? "warn" : "neutral"}>{quality.missing_candles} missing</Pill>
          <Pill tone={quality.duplicates_removed ? "warn" : "neutral"}>{quality.duplicates_removed} duplicates removed</Pill>
          <Pill tone={quality.invalid_rows_removed ? "warn" : "neutral"}>{quality.invalid_rows_removed} invalid removed</Pill>
          <Pill tone={quality.is_stale ? "bad" : "good"}>{quality.is_stale ? "stale" : "fresh"} · age {fmtAge(quality.age_seconds)}</Pill>
        </div>
      )}
    </Card>
  );
}
