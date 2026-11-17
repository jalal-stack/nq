const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

export const fmtUsd = (v: number | string | null | undefined): string =>
  v === null || v === undefined || v === "" || Number.isNaN(Number(v)) ? "—" : usd.format(Number(v));

export const fmtPct = (v: number | null | undefined, digits = 1): string =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`;

export const fmtNum = (v: number | string | null | undefined, digits = 2): string =>
  v === null || v === undefined || v === "" || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(digits);

export function fmtAge(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 90) return `${Math.round(seconds)}s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}

export const humanize = (code: string): string =>
  code.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

// Neutral names for risk check codes (codes are named after the failure they guard against).
const CHECK_LABELS: Record<string, string> = {
  stop_side: "Stop placement",
  stop_too_wide: "Stop distance",
  stop_too_tight: "Stop vs ATR",
  stale_data: "Data freshness",
  abnormal_volatility: "Volatility",
  wide_spread: "Spread",
  session_closed: "Trading session",
  daily_loss: "Daily loss limit",
  max_drawdown: "Drawdown limit",
  max_open_positions: "Open positions",
  correlated_positions: "Correlated positions",
  duplicate_position: "Existing position",
  exposure: "Gross exposure",
  size_too_small: "Minimum size",
  size_reduced: "Size capped",
};

export const checkLabel = (code: string): string => CHECK_LABELS[code] ?? humanize(code);
