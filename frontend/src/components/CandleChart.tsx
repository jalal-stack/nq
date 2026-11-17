import {
  CandlestickSeries,
  ColorType,
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { CandleRow } from "../lib/api";

const toTime = (ts: string) => Math.floor(Date.parse(ts) / 1000) as UTCTimestamp;

export function CandleChart({ candles, live }: { candles: CandleRow[]; live: CandleRow | null }) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<{
    candles: ISeriesApi<"Candlestick">;
    ema20: ISeriesApi<"Line">;
    ema50: ISeriesApi<"Line">;
  } | null>(null);

  useEffect(() => {
    if (!el.current) return;
    const c = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#94a3b8" },
      grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } },
      rightPriceScale: { borderColor: "#334155" },
      timeScale: { borderColor: "#334155", timeVisible: true },
    });
    series.current = {
      candles: c.addSeries(CandlestickSeries, {
        upColor: "#10b981", downColor: "#f43f5e", wickUpColor: "#10b981", wickDownColor: "#f43f5e", borderVisible: false,
      }),
      ema20: c.addSeries(LineSeries, { color: "#38bdf8", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
      ema50: c.addSeries(LineSeries, { color: "#f59e0b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
    };
    chart.current = c;
    return () => {
      c.remove();
      chart.current = null;
      series.current = null;
    };
  }, []);

  useEffect(() => {
    const s = series.current;
    if (!s) return;
    s.candles.setData(candles.map((r) => ({ time: toTime(r.ts), open: r.open, high: r.high, low: r.low, close: r.close })));
    const line = (key: "ema_20" | "ema_50") =>
      candles.filter((r) => r[key] != null).map((r) => ({ time: toTime(r.ts), value: r[key] as number }));
    s.ema20.setData(line("ema_20"));
    s.ema50.setData(line("ema_50"));
    chart.current?.timeScale().fitContent();
  }, [candles]);

  useEffect(() => {
    const s = series.current;
    if (!s || !live || candles.length === 0) return;
    // Ignore updates older than the loaded history (e.g. a switch of symbol mid-stream).
    if (toTime(live.ts) < toTime(candles[candles.length - 1].ts)) return;
    s.candles.update({ time: toTime(live.ts), open: live.open, high: live.high, low: live.low, close: live.close });
  }, [live, candles]);

  return <div ref={el} className="h-[380px] w-full" data-testid="candle-chart" />;
}
