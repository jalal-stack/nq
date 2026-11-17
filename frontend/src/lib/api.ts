// Typed client for the TradeMind FastAPI backend (/api/v1).

const RAW_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";
export const API_BASE = RAW_BASE.replace(/\/+$/, "");
export const API_ROOT = `${API_BASE}/api/v1`;

export function wsUrl(path: string, params: Record<string, string>): string {
  const url = new URL(`${API_ROOT}${path}`);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  return url.toString();
}

export type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "1d";
export type Provider = "synthetic" | "ccxt" | "yfinance";
export type AssetClass = "crypto" | "stock" | "forex";

export interface Health {
  status: string;
  version: string;
  mode: string;
  live_execution_enabled: boolean;
}

export interface DataQuality {
  rows: number;
  duplicates_removed: number;
  invalid_rows_removed: number;
  missing_candles: number;
  last_ts: string | null;
  age_seconds: number | null;
  is_stale: boolean;
}

export interface CandleRow {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema_20?: number | null;
  ema_50?: number | null;
}

export interface OhlcvResponse {
  symbol: string;
  provider: string;
  timeframe: Timeframe;
  realtime: boolean;
  quality: DataQuality;
  candles: CandleRow[];
}

export interface PerformanceReport {
  trades: number;
  net_profit: number;
  total_fees: number;
  win_rate: number | null;
  profit_factor: number | null;
  expectancy: number | null;
  average_win: number | null;
  average_loss: number | null;
  max_drawdown: number;
  sharpe: number | null;
  sortino: number | null;
  trades_per_day: number | null;
  exposure: number | null;
  sample_warning: string | null;
}

export interface BacktestResult {
  strategy: string;
  symbol: string;
  bars: number;
  signals: number;
  risk_rejections: Record<string, number>;
  report: PerformanceReport;
}

export interface RiskCheck {
  code: string;
  passed: boolean;
  detail: string;
}

export interface RiskDecision {
  approved: boolean;
  quantity: string;
  notional: string;
  risk_amount: string;
  reward_risk: string | null;
  checks: RiskCheck[];
}

export interface RiskRequest {
  proposal: {
    instrument: { symbol: string; asset_class: AssetClass; lot_size?: string };
    side: "buy" | "sell";
    entry_price: string;
    stop_loss: string;
    take_profit?: string;
    strategy: string;
  };
  portfolio: { equity: string; peak_equity: string; day_start_equity: string };
  context: { as_of: string; last_data_ts: string; atr?: string };
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  ohlcv: (provider: Provider, symbol: string, timeframe: Timeframe, limit = 300) =>
    request<OhlcvResponse>(
      `/market/${provider}/ohlcv?` +
        new URLSearchParams({ symbol, timeframe, limit: String(limit), indicators: "true" }),
    ),
  backtest: (body: { symbol: string; provider: Provider; timeframe: Timeframe; bars: number; asset_class: AssetClass }) =>
    request<BacktestResult>("/backtest", { method: "POST", body: JSON.stringify(body) }),
  evaluateRisk: (body: RiskRequest) =>
    request<RiskDecision>("/risk/evaluate", { method: "POST", body: JSON.stringify(body) }),
};
