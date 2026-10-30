"use client";

import clsx from "clsx";
import { useState } from "react";
import { ChartLegend, VarPnlChart } from "@/components/charts";
import { ModelControls, modelName } from "@/components/controls";
import { useSelection } from "@/components/selection";
import { Card, PageHeader, Skeleton, StatusPill } from "@/components/ui";
import { useApi } from "@/lib/api";
import { demoBacktests, demoHistory } from "@/lib/demo";
import { confLabel } from "@/lib/format";
import type { BacktestRow, RiskHistory } from "@/lib/types";

const p = (v: number) => (v < 0.001 ? "<0.001" : v.toFixed(3));

export default function Backtests() {
  const { model, confidence, setModel } = useSelection();
  const [scope, setScope] = useState<"rolling_250" | "full">("rolling_250");
  const bt = useApi<BacktestRow[]>("/backtest", demoBacktests);
  const hist = useApi<RiskHistory>(`/risk/history?model=${model}&confidence=${confidence}`, () => demoHistory(model, confidence));
  const rows = (bt.data ?? []).filter((r) => r.scope === scope && r.confidence === confidence);
  const pts = scope === "rolling_250" ? (hist.data?.points.slice(-251) ?? []) : (hist.data?.points ?? []);

  return (
    <>
      <PageHeader eyebrow="Kupiec POF · Christoffersen independence · Basel traffic light" title="Do the models hold up?" demo={bt.demo || hist.demo}>
        <ModelControls />
      </PageHeader>

      <Card title={`${modelName(model)}: P&L against −VaR`} action={<ChartLegend />}>
        {pts.length ? <VarPnlChart points={pts} height={320} /> : <Skeleton className="h-[320px]" />}
      </Card>

      <Card
        title={`All models at ${confLabel(confidence)}`}
        subtitle="Reject at 5%: Kupiec or Christoffersen p < 0.05. Click a row to chart that model."
        action={
          <div role="group" aria-label="Window" className="flex gap-1 rounded-full border border-line bg-white p-1">
            {(["rolling_250", "full"] as const).map((s) => (
              <button key={s} type="button" aria-pressed={scope === s} onClick={() => setScope(s)} className={clsx("pill", scope === s ? "bg-sage-600 text-white" : "text-ink-2 hover:bg-sage-50")}>
                {s === "full" ? "Full history" : "Last 250 days"}
              </button>
            ))}
          </div>
        }
      >
        {bt.data ? (
          <div className="-mx-2 overflow-x-auto">
            <table className="w-full min-w-[760px] border-separate border-spacing-y-1 text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  <th className="px-3 py-1.5">Model</th>
                  <th className="px-3 py-1.5 text-right">Days</th>
                  <th className="px-3 py-1.5 text-right">Exceptions</th>
                  <th className="px-3 py-1.5 text-right">Expected</th>
                  <th className="px-3 py-1.5 text-right">Kupiec LR · p</th>
                  <th className="px-3 py-1.5 text-right">Christoffersen LR · p</th>
                  <th className="px-3 py-1.5 text-right">Cond. coverage p</th>
                  <th className="px-3 py-1.5">Zone</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.model}
                    onClick={() => setModel(r.model)}
                    className={clsx("cursor-pointer transition-colors", r.model === model ? "bg-sage-100" : "hover:bg-canvas")}
                  >
                    <td className="rounded-l-xl px-3 py-2.5">
                      <button type="button" onClick={() => setModel(r.model)} className="text-left font-semibold">
                        {modelName(r.model)}
                      </button>
                    </td>
                    <td className="num px-3 py-2.5 text-right text-ink-2">{r.T}</td>
                    <td className="num px-3 py-2.5 text-right font-semibold">{r.exceptions}</td>
                    <td className="num px-3 py-2.5 text-right text-ink-2">{r.expected.toFixed(1)}</td>
                    <td className={clsx("num px-3 py-2.5 text-right", r.p_pof < 0.05 ? "font-bold text-coral-700" : "text-ink-2")}>
                      {r.lr_pof.toFixed(2)} · {p(r.p_pof)}
                    </td>
                    <td className={clsx("num px-3 py-2.5 text-right", r.p_ind < 0.05 ? "font-bold text-coral-700" : "text-ink-2")}>
                      {r.lr_ind.toFixed(2)} · {p(r.p_ind)}
                    </td>
                    <td className={clsx("num px-3 py-2.5 text-right", r.p_cc < 0.05 ? "font-bold text-coral-700" : "text-ink-2")}>{p(r.p_cc)}</td>
                    <td className="rounded-r-xl px-3 py-2.5">
                      <StatusPill status={r.zone} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Skeleton className="h-[380px]" />
        )}
      </Card>
    </>
  );
}
