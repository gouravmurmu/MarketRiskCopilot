"use client";

import clsx from "clsx";
import { RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { LimitBars } from "@/components/charts";
import { modelName } from "@/components/controls";
import { Card, PageHeader, Skeleton } from "@/components/ui";
import { apiConfigured, apiPost, useApi } from "@/lib/api";
import { demoPortfolio, demoWhatIf } from "@/lib/demo";
import { ASSET_COLOR, signedK, signedPct, usdK } from "@/lib/format";
import type { Portfolio, WhatIfRequest, WhatIfResult } from "@/lib/types";

const PRESETS: { label: string; changes: (base: Record<string, number>) => Record<string, number> }[] = [
  { label: "Halve NVDA", changes: (b) => ({ NVDA: b.NVDA / 2 }) },
  { label: "Cut equities 20%", changes: (b) => Object.fromEntries(["SPY", "QQQ", "NVDA", "AAPL", "XLF", "EFA", "INDA"].map((t) => [t, b[t] * 0.8])) },
  { label: "Double gold", changes: (b) => ({ GLD: b.GLD * 2 }) },
  { label: "Add $500k TLT", changes: (b) => ({ TLT: b.TLT + 500_000 }) },
];

export default function WhatIf() {
  const port = useApi<Portfolio>("/portfolio", demoPortfolio);
  const base = useMemo(() => Object.fromEntries(port.data?.positions.map((p) => [p.ticker, p.notional_usd]) ?? []), [port.data]);
  const [target, setTarget] = useState<Record<string, number>>({});
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [demo, setDemo] = useState(!apiConfigured);
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    if (!port.data) return;
    const changed = Object.fromEntries(Object.entries(target).filter(([t, v]) => Math.abs(v - (base[t] ?? 0)) > 1));
    const req: WhatIfRequest = { set_exposure: changed, models: ["hs_500", "pn_ewma", "mc_ewma"] };
    const id = ++seq.current;
    const timer = setTimeout(async () => {
      setBusy(true);
      let res: WhatIfResult;
      try {
        res = apiConfigured && !port.demo ? await apiPost<WhatIfResult>("/whatif", req) : demoWhatIf(req);
        if (id === seq.current) setDemo(!apiConfigured || port.demo);
      } catch {
        res = demoWhatIf(req);
        if (id === seq.current) setDemo(true);
      }
      if (id === seq.current) {
        setResult(res);
        setBusy(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [target, base, port.data, port.demo]);

  const value = (t: string) => target[t] ?? base[t] ?? 0;
  const set = (t: string, v: number) => setTarget((cur) => ({ ...cur, [t]: v }));
  const dirty = Object.entries(target).some(([t, v]) => Math.abs(v - (base[t] ?? 0)) > 1);
  const headline = result?.figures.find((f) => f.model === "hs_500" && f.confidence === 0.99);

  return (
    <>
      <PageHeader eyebrow="Reprices with the same engine as the daily run · nothing is saved" title="What if we traded?" demo={demo}>
        <button type="button" className="btn-ghost" onClick={() => setTarget({})} disabled={!dirty}>
          <RotateCcw size={16} aria-hidden="true" /> Reset
        </button>
      </PageHeader>

      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button key={p.label} type="button" className="pill border border-line bg-white text-ink-2 hover:bg-sage-50" onClick={() => setTarget(p.changes(base))}>
            {p.label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-start gap-5">
        <Card className="flex-[3_1_460px]" title="Position sizes" subtitle="Drag a slider or type a USD amount">
          {port.data ? (
            <ul className="flex flex-col gap-1">
              {port.data.positions.map((p) => {
                const v = value(p.ticker);
                const changed = Math.abs(v - p.notional_usd) > 1;
                return (
                  <li key={p.ticker} className={clsx("grid grid-cols-[minmax(84px,auto)_1fr_auto] items-center gap-3 rounded-xl px-2 py-2", changed && "bg-sage-50")}>
                    <label htmlFor={`s-${p.ticker}`} className="flex items-center gap-2 text-sm font-semibold">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: ASSET_COLOR[p.asset_class] }} />
                      {p.ticker}
                    </label>
                    <input
                      id={`s-${p.ticker}`}
                      type="range"
                      min={0}
                      max={Math.max(2 * p.notional_usd, 1_000_000)}
                      step={10_000}
                      value={v}
                      onChange={(e) => set(p.ticker, Number(e.target.value))}
                      className="h-11 w-full accent-sage-600"
                    />
                    <div className="flex items-center gap-2">
                      <input
                        aria-label={`${p.ticker} exposure in USD`}
                        type="number"
                        min={0}
                        step={10_000}
                        value={Math.round(v)}
                        onChange={(e) => set(p.ticker, Math.max(0, Number(e.target.value)))}
                        className="num min-h-11 w-28 rounded-xl border border-line bg-white px-3 text-right text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-sage-600"
                      />
                      <span className={clsx("num w-16 text-right text-xs font-semibold", changed ? "text-sage-700" : "text-transparent")}>
                        {changed ? signedK(v - p.notional_usd) : "0"}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <Skeleton className="h-[560px]" />
          )}
        </Card>

        <div className="flex min-w-0 flex-[2_1_320px] flex-col gap-5 lg:sticky lg:top-24">
          <Card title="Impact" subtitle={busy ? "Repricing…" : "1-day VaR before → after"}>
            {headline ? (
              <div className={clsx("transition-opacity", busy && "opacity-60")}>
                <div className="rounded-2xl bg-canvas p-4">
                  <div className="text-[13px] font-semibold text-ink-muted">{modelName("hs_500")}, 99%</div>
                  <div className="num mt-1 flex flex-wrap items-baseline gap-x-3 text-3xl font-bold tracking-tight">
                    {usdK(headline.var_after)}
                    <span className={clsx("text-base font-semibold", headline.var_after > headline.var_before ? "text-apricot-700" : "text-sage-700")}>
                      {signedK(headline.var_after - headline.var_before)} ({signedPct(headline.var_after / headline.var_before - 1)})
                    </span>
                  </div>
                  <div className="num text-sm text-ink-muted">was {usdK(headline.var_before)}</div>
                </div>
                <ul className="mt-3 flex flex-col gap-1.5 text-sm">
                  {result?.figures
                    .filter((f) => !(f.model === "hs_500" && f.confidence === 0.99))
                    .map((f) => (
                      <li key={f.model + f.confidence} className="flex justify-between gap-2 px-1">
                        <span className="text-ink-2">
                          {modelName(f.model)}, {f.confidence === 0.99 ? "99%" : "97.5%"}
                        </span>
                        <span className="num">
                          {usdK(f.var_before)} → <strong>{usdK(f.var_after)}</strong>
                        </span>
                      </li>
                    ))}
                </ul>
              </div>
            ) : (
              <Skeleton className="h-[200px]" />
            )}
          </Card>
          <Card title="Limits after the trade">{result ? <LimitBars items={result.limits_after} /> : <Skeleton className="h-[240px]" />}</Card>
        </div>
      </div>
    </>
  );
}
