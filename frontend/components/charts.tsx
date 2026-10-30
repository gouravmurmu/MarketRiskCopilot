"use client";

import clsx from "clsx";
import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { ASSET_COLOR, EFFECT_LABEL, longDate, pct, shortDate, signedK, usdK } from "@/lib/format";
import type { Contribution, Effect, HistoryPoint, LimitItem } from "@/lib/types";

export function KpiTile({ label, value, delta, tone = "flat" }: {
  label: string;
  value: string;
  delta?: string;
  tone?: "up" | "down" | "flat";
}) {
  return (
    <div className="card flex min-w-0 animate-rise flex-col gap-1.5 !p-4 sm:!p-5">
      <span className="text-[13px] font-semibold text-ink-muted">{label}</span>
      <span className="num text-2xl font-bold leading-tight tracking-tight sm:text-[30px]">{value}</span>
      {delta && (
        <span className={clsx("text-[13px] font-semibold", tone === "up" ? "text-apricot-700" : tone === "down" ? "text-sage-600" : "text-ink-muted")}>
          {delta}
        </span>
      )}
    </div>
  );
}

export function LimitBars({ items }: { items: LimitItem[] }) {
  return (
    <ul className="flex flex-col gap-3.5">
      {items.map((l) => {
        const fill = l.status === "breach" ? "bg-coral-400" : l.status === "warning" ? "bg-apricot-400" : "bg-sage-400";
        return (
          <li key={l.scope}>
            <div className="mb-1.5 flex justify-between gap-2 text-sm">
              <span className="font-semibold">{l.scope}</span>
              <span className="num text-ink-2">
                {usdK(l.value_usd)} / {usdK(l.limit_usd, 0)}
                <span
                  className={clsx(
                    "ml-1.5 rounded-full px-2 py-px text-xs font-bold",
                    l.status === "breach" ? "bg-coral-100 text-coral-700" : l.status === "warning" ? "bg-apricot-100 text-apricot-700" : "bg-sage-100 text-sage-700",
                  )}
                >
                  {pct(l.utilisation)}
                </span>
              </span>
            </div>
            <div
              className="relative h-2.5 overflow-hidden rounded-full bg-sage-50"
              role="meter"
              aria-label={`${l.scope} limit utilisation`}
              aria-valuenow={Math.round(l.utilisation * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div className={clsx("absolute inset-y-0 left-0 origin-left animate-grow rounded-full", fill)} style={{ width: `${Math.min(100, l.utilisation * 100)}%` }} />
              <div className="absolute inset-y-0 w-0.5 bg-white" style={{ left: `${l.warn_pct * 100}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

type ChartRow = { date: string; negVar: number; pnl: number | null; exc: number | null };

export function VarPnlChart({ points, height = 280 }: { points: HistoryPoint[]; height?: number }) {
  const rows: ChartRow[] = points.map((p) => ({
    date: p.date,
    negVar: -p.var_usd,
    pnl: p.pnl_usd,
    exc: p.exception ? p.pnl_usd : null,
  }));
  return (
    <div style={{ height }} role="img" aria-label="Daily P&L bars against the negative VaR line, with exceptions marked">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap="15%">
          <CartesianGrid vertical={false} stroke="#EEF2EC" />
          <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 12, fill: "#56655A" }} tickLine={false} axisLine={false} minTickGap={48} />
          <YAxis tickFormatter={(v) => usdK(v, 0)} tick={{ fontSize: 12, fill: "#56655A" }} tickLine={false} axisLine={false} width={64} />
          <ReferenceLine y={0} stroke="#DCE8D9" />
          <Tooltip
            cursor={{ fill: "#EEF2EC" }}
            contentStyle={{ borderRadius: 14, border: "1px solid #E1E8DE", boxShadow: "0 6px 24px rgba(30,42,33,.08)", fontSize: 13 }}
            labelFormatter={(d) => shortDate(String(d))}
            formatter={(v: number, name: string) => [usdK(v), name === "negVar" ? "−VaR" : name === "pnl" ? "Next-day P&L" : "Exception"]}
          />
          <Bar dataKey="pnl" fill="#BCD3B8" isAnimationActive />
          <Line dataKey="negVar" stroke="#5E8A66" strokeWidth={2.5} dot={false} type="monotone" isAnimationActive />
          <Scatter dataKey="exc" fill="#D9785F" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ChartLegend() {
  return (
    <div className="flex flex-wrap gap-4 text-[13px] text-ink-muted">
      <span className="inline-flex items-center gap-1.5"><span className="h-[3px] w-3.5 rounded bg-sage-500" />−VaR</span>
      <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-[3px] bg-sage-300" />Next-day P&amp;L</span>
      <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-coral-400" />Exception</span>
    </div>
  );
}

export function effectNote(e: Effect): string {
  const amt = signedK(e.amount_usd);
  switch (e.effect) {
    case "position": {
      const ch = Object.entries(e.detail.changes ?? {});
      if (!ch.length) return `Position effect ${amt}: no position changes since yesterday.`;
      return `Position effect ${amt}: ${ch.map(([t, c]) => `${t} ${usdK(c.from, 0)} → ${usdK(c.to, 0)}`).join(", ")}. Measured as today's book on yesterday's market data.`;
    }
    case "volatility": {
      const vols = Object.entries(e.detail.daily_vol ?? {})
        .map(([t, v]) => ({ t, r: v.to / v.from - 1 }))
        .sort((a, b) => Math.abs(b.r) - Math.abs(a.r))
        .slice(0, 3);
      return `Volatility effect ${amt}, holding correlations at yesterday's levels.${vols.length ? ` Largest vol moves: ${vols.map((v) => `${v.t} ${v.r >= 0 ? "+" : ""}${(v.r * 100).toFixed(0)}%`).join(", ")}.` : ""}`;
    }
    case "correlation":
      return `Correlation effect ${amt}: the rest of the market-data move, from co-movements changing.`;
    case "window_roll": {
      const d = e.detail.dropped?.[0];
      const a = e.detail.added?.[0];
      return `Window roll ${amt}: ${d ? `${longDate(d.date)} (P&L ${usdK(d.pnl)}${d.in_tail ? ", in the tail" : ""}) dropped out` : "nothing dropped"}${a ? ` and ${longDate(a.date)} (P&L ${usdK(a.pnl)}${a.in_tail ? ", in the tail" : ""}) entered` : ""}.`;
    }
    default:
      return `Market data effect ${amt}: everything that moved apart from positions.`;
  }
}

export function Waterfall({ previous, current, effects, height = 200 }: {
  previous: number;
  current: number;
  effects: Effect[];
  height?: number;
}) {
  const [picked, setPicked] = useState<string>(() =>
    effects.length ? [...effects].sort((a, b) => Math.abs(b.amount_usd) - Math.abs(a.amount_usd))[0].effect : "today",
  );
  type Col = { id: string; label: string; lo: number; hi: number; amount: string; color: string; note: string };
  let run = previous;
  const cols: Col[] = [
    { id: "prev", label: "Yesterday", lo: 0, hi: previous, amount: usdK(previous), color: "bg-sage-500", note: "Yesterday's VaR on the same model and confidence." },
    ...effects.map((e) => {
      const lo = Math.min(run, run + e.amount_usd);
      const hi = Math.max(run, run + e.amount_usd);
      run += e.amount_usd;
      return { id: e.effect, label: EFFECT_LABEL[e.effect] ?? e.effect, lo, hi, amount: signedK(e.amount_usd), color: e.amount_usd >= 0 ? "bg-apricot-400" : "bg-sky-400", note: effectNote(e) };
    }),
    { id: "today", label: "Today", lo: 0, hi: current, amount: usdK(current), color: "bg-sage-500", note: `Today's VaR. The effects add up exactly to the ${signedK(current - previous)} change.` },
  ];
  const max = Math.max(...cols.map((c) => c.hi)) * 1.08;
  const active = cols.find((c) => c.id === picked) ?? cols[cols.length - 1];
  return (
    <div>
      <div className="grid items-end gap-2 sm:gap-3" style={{ gridTemplateColumns: `repeat(${cols.length}, minmax(0, 1fr))` }}>
        {cols.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => setPicked(c.id)}
            aria-pressed={c.id === active.id}
            className="group flex min-w-0 flex-col items-stretch gap-2 rounded-xl text-center focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sage-600"
          >
            <span className="num truncate text-[13px] font-bold">{c.amount}</span>
            <span className="relative block" style={{ height }}>
              <span
                className={clsx(
                  "absolute inset-x-[12%] rounded-lg transition-all duration-500 group-hover:brightness-95",
                  c.color,
                  c.id === active.id && "ring-2 ring-sage-600 ring-offset-2",
                )}
                style={{ bottom: `${(c.lo / max) * height}px`, height: `${Math.max(3, ((c.hi - c.lo) / max) * height)}px` }}
              />
            </span>
            <span className={clsx("truncate text-[13px]", c.id === active.id ? "font-bold text-ink" : "text-ink-muted")}>{c.label}</span>
          </button>
        ))}
      </div>
      <p className="mt-4 rounded-2xl bg-canvas px-4 py-3.5 text-sm text-ink-2" aria-live="polite">{active.note}</p>
    </div>
  );
}

export function AssetClassBar({ items }: { items: Contribution[] }) {
  const total = items.reduce((a, i) => a + Math.max(0, i.component_var), 0) || 1;
  return (
    <div>
      <div className="flex h-[18px] gap-0.5 overflow-hidden rounded-full" aria-hidden="true">
        {items.map((i) => (
          <span key={i.key} className="block h-full origin-left animate-grow" style={{ flex: `${Math.max(0, i.component_var)} 1 0`, background: ASSET_COLOR[i.key] ?? "#BCD3B8" }} />
        ))}
      </div>
      <ul className="mt-4 flex flex-col gap-2.5">
        {items.map((i) => (
          <li key={i.key} className="flex items-center gap-2.5 text-sm">
            <span className="h-3 w-3 shrink-0 rounded" style={{ background: ASSET_COLOR[i.key] ?? "#BCD3B8" }} />
            <span className="flex-1 font-semibold">{i.key}</span>
            <span className="num text-ink-2">{usdK(i.component_var)}</span>
            <span className="num w-11 text-right text-ink-muted">{pct(Math.max(0, i.component_var) / total)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
