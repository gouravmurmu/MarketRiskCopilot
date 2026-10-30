"use client";

import { AssetClassBar } from "@/components/charts";
import { ModelControls, modelName } from "@/components/controls";
import { useSelection } from "@/components/selection";
import { Card, PageHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { demoContributors, demoPortfolio } from "@/lib/demo";
import { ASSET_COLOR, pct, usdK } from "@/lib/format";
import type { Contributors, Portfolio } from "@/lib/types";

export default function Breakdown() {
  const { model, confidence } = useSelection();
  const q = `model=${model}&confidence=${confidence}`;
  const pos = useApi<Contributors>(`/risk/contributors?${q}&level=position`, () => demoContributors(model, confidence, "position"));
  const cls = useApi<Contributors>(`/risk/contributors?${q}&level=asset_class`, () => demoContributors(model, confidence, "asset_class"));
  const port = useApi<Portfolio>("/portfolio", demoPortfolio);
  const meta = new Map(port.data?.positions.map((p) => [p.ticker, p]) ?? []);
  const maxAbs = Math.max(1, ...(pos.data?.items.map((i) => Math.abs(i.component_var)) ?? [1]));

  return (
    <>
      <PageHeader eyebrow="Euler allocation · components sum to total VaR" title="Risk breakdown" demo={pos.demo || cls.demo}>
        <ModelControls />
      </PageHeader>
      <div className="flex flex-wrap gap-5">
        <Card className="flex-[1_1_300px]" title="By asset class" subtitle={pos.data ? `Total ${usdK(pos.data.total_var_usd)} · ${modelName(model)}` : undefined}>
          {cls.data ? <AssetClassBar items={cls.data.items} /> : <Skeleton className="h-[220px]" />}
        </Card>
        <Card className="flex-[3_1_520px]" title="By position" subtitle="Marginal VaR is the VaR change per extra $1 held">
          {pos.data ? (
            <div className="-mx-2 overflow-x-auto">
              <table className="w-full min-w-[560px] border-separate border-spacing-y-1 text-sm">
                <thead>
                  <tr className="text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
                    <th className="px-2 py-1.5">Position</th>
                    <th className="px-2 py-1.5 text-right">Exposure</th>
                    <th className="w-[38%] px-2 py-1.5">Component VaR</th>
                    <th className="px-2 py-1.5 text-right">Share</th>
                    <th className="px-2 py-1.5 text-right">Marginal per $1k</th>
                  </tr>
                </thead>
                <tbody>
                  {pos.data.items.map((i) => {
                    const p = meta.get(i.key);
                    return (
                      <tr key={i.key} className="transition-colors hover:bg-canvas">
                        <td className="rounded-l-xl px-2 py-2">
                          <div className="flex items-center gap-2.5">
                            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: ASSET_COLOR[p?.asset_class ?? ""] ?? "#BCD3B8" }} />
                            <div className="min-w-0">
                              <div className="font-semibold">{i.key}</div>
                              <div className="truncate text-xs text-ink-muted">{p?.name}</div>
                            </div>
                          </div>
                        </td>
                        <td className="num px-2 py-2 text-right text-ink-2">{usdK(i.exposure_usd, 0)}</td>
                        <td className="px-2 py-2">
                          <div className="flex items-center gap-2">
                            <div className="h-2 flex-1 overflow-hidden rounded-full bg-sage-50">
                              <div
                                className={`h-full origin-left animate-grow rounded-full ${i.component_var >= 0 ? "bg-sage-400" : "bg-sky-400"}`}
                                style={{ width: `${(Math.abs(i.component_var) / maxAbs) * 100}%` }}
                              />
                            </div>
                            <span className="num w-16 text-right font-semibold">{usdK(i.component_var)}</span>
                          </div>
                        </td>
                        <td className="num px-2 py-2 text-right text-ink-2">{pct(i.share, 1)}</td>
                        <td className="num rounded-r-xl px-2 py-2 text-right text-ink-2">${(i.marginal_var * 1000).toFixed(1)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="subtle mt-3 px-2">Negative components are hedges: adding to them lowers portfolio VaR.</p>
            </div>
          ) : (
            <Skeleton className="h-[420px]" />
          )}
        </Card>
      </div>
    </>
  );
}
