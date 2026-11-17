import type { ReactNode } from "react";

export function Card({ title, actions, children, className = "" }: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-slate-800 bg-slate-900/60 ${className}`}>
      <header className="flex items-center justify-between gap-3 border-b border-slate-800 px-4 py-2.5">
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        {actions}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({ label, value, tone = "neutral" }: {
  label: string;
  value: string;
  tone?: "neutral" | "good" | "bad";
}) {
  const color = tone === "good" ? "text-emerald-400" : tone === "bad" ? "text-rose-400" : "text-slate-100";
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`font-mono text-base tabular-nums ${color}`}>{value}</div>
    </div>
  );
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "bad" }) {
  const cls = {
    neutral: "border-slate-700 text-slate-300",
    good: "border-emerald-700/60 bg-emerald-950/40 text-emerald-300",
    warn: "border-amber-700/60 bg-amber-950/40 text-amber-300",
    bad: "border-rose-700/60 bg-rose-950/40 text-rose-300",
  }[tone];
  return <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${cls}`}>{children}</span>;
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return <p className="rounded-md border border-rose-800/60 bg-rose-950/40 px-3 py-2 text-sm text-rose-300">{error}</p>;
}
