"use client";

import Link from "next/link";
import { AssetClassBar, ChartLegend, KpiTile, LimitBars, VarPnlChart, Waterfall } from "@/components/charts";
import { ModelControls, modelName } from "@/components/controls";
import { useSelection } from "@/components/selection";
import { Card, PageHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { demoAttribution, demoBacktests, demoContributors, demoHistory, demoLimits, demoSummary } from "@/lib/demo";
import { confLabel, pct, signedPct, usdK } from "@/lib/format";
import type { Attribution, BacktestRow, Contributors, Limits, RiskHistory, RiskSummary } from "@/lib/types";

function headline(change: number | null | undefined, limits: Limits | undefined) {
  const move =
    change == null ? "Today's risk at a glance" : Math.abs(change) < 0.02 ? "VaR broadly unchanged" : `VaR ${change > 0 ? "up" : "down"} ${Math.abs(change * 100).toFixed(0)}% overnight`;
  const flagged = limits?.items.filter((l) => l.status !== "ok") ?? [];
  if (!flagged.length) return `${move}, all limits green`;
  const worst = flagged.sort((a, b) => b.utilisation - a.utilisation)[0];
  return `${move}, ${worst.scope.toLowerCase()} limit ${worst.status === "breach" ? "in breach" : "in amber"}`;
}

export default function Overview() {
  const { model, confidence } = useSelection();
  const q = `model=${model}&confidence=${confidence}`;
  const summary = useApi<RiskSummary>("/risk/summary", demoSummary);
  const history = useApi<RiskHistory>(`/risk/history?${q}`, () => demoHistory(model, confidence));
  const limits = useApi<Limits>("/limits", demoLimits);
  const attr = useApi<Attribution>(`/risk/attribution?${q}`, () => demoAttribution(model, confidence));
  const classes = useApi<Contributors>(`/risk/contributors?${q}&level=asset_class`, () => demoContributors(model, confidence, "asset_class"));
  const positions = useApi<Contributors>(`/risk/contributors?${q}&level=position`, () => demoContributors(model, confidence, "position"));
  const bt = useApi<BacktestRow[]>(`/backtest?model=${model}&confidence=${confidence}&scope=rolling_250`, demoBacktests);

  const fig = summary.data?.figures.find((f) => f.model === model && f.confidence === confidence);
  const svar = summary.data?.figures.find((f) => f.model === "svar" && f.confidence === confidence);
  const demo = [summary, history, limits, attr, classes].some((x) => x.demo);
  const pts = history.data?.points.slice(-120) ?? [];
  const btRow = bt.data?.find((b) => b.model === model && b.confidence === confidence && b.scope === "rolling_250");
  const top = positions.data?.items[0];

  return (
    <>
      <PageHeader eyebrow="Sample $10M multi-asset portfolio" title={summary.data ? headline(fig?.change_pct, limits.data) : "Loading today's risk…"} demo={demo}>
        <ModelControls showAll={false} />
      </PageHeader>

      <section aria-label="Headline risk numbers" className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {fig ? (
          <>
            <KpiTile
              label={`1-day VaR, ${confLabel(confidence)}`}
              value={usdK(fig.var_usd)}
              delta={fig.change_pct == null ? undefined : `${fig.change_pct >= 0 ? "▲" : "▼"} ${signedPct(fig.change_pct)} vs yesterday`}
              tone={fig.change_pct == null ? "flat" : fig.change_pct > 0 ? "up" : "down"}
            />
            <KpiTile label="Expected Shortfall" value={usdK(fig.es_usd)} delta={`${pct(fig.es_usd / fig.var_usd - 1)} beyond VaR`} />
            <KpiTile label="10-day VaR (√10 scaling)" value={usdK(fig.var_10d_usd)} delta="Assumes i.i.d. returns" />
            <KpiTile label="Stressed VaR" value={svar ? usdK(svar.var_usd) : "—"} delta="Window Feb 2020 – Jan 2021" />
          </>
        ) : (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[120px]" />)
        )}
      </section>

      <div className="flex flex-wrap gap-5">
        <Card
          className="flex-[3_1_440px]"
          title="VaR vs next-day P&L"
          subtitle={`${modelName(model)}, last ${pts.length} days`}
          action={<ChartLegend />}
        >
          {pts.length ? <VarPnlChart points={pts} /> : <Skeleton className="h-[280px]" />}
          {btRow && (
            <p className="subtle mt-3">
              {btRow.exceptions} exception{btRow.exceptions === 1 ? "" : "s"} in the last 250 days (expected {btRow.expected.toFixed(1)}) · Basel zone{" "}
              <strong className={btRow.zone === "green" ? "text-sage-700" : btRow.zone === "yellow" ? "text-apricot-700" : "text-coral-700"}>{btRow.zone}</strong> · Kupiec p = {btRow.p_pof.toFixed(2)} ·{" "}
              <Link href="/backtests">All backtests</Link>
            </p>
          )}
        </Card>
        <Card className="flex-[2_1_300px]" title="Limit utilisation" action={<span className="text-xs text-ink-muted">1-day 99% VaR, {modelName(limits.data?.model ?? "hs_500")}</span>}>
          {limits.data ? <LimitBars items={limits.data.items} /> : <Skeleton className="h-[260px]" />}
        </Card>
      </div>

      <div className="flex flex-wrap gap-5">
        <Card className="flex-[3_1_440px]" title="Why did VaR move?" subtitle="Click a bar for the detail · effects sum exactly to the change" action={<Link href="/attribution" className="text-sm font-semibold">Full breakdown</Link>}>
          {attr.data && attr.data.previous_var_usd != null ? (
            <Waterfall key={`${model}-${confidence}`} previous={attr.data.previous_var_usd} current={attr.data.var_usd} effects={attr.data.effects} />
          ) : attr.loading ? (
            <Skeleton className="h-[260px]" />
          ) : (
            <p className="subtle">No previous day to compare with yet.</p>
          )}
        </Card>
        <Card className="flex-[2_1_300px]" title="Where the risk sits" subtitle="Component VaR by asset class">
          {classes.data ? <AssetClassBar items={classes.data.items} /> : <Skeleton className="h-[220px]" />}
          {top && (
            <p className="subtle mt-4">
              Largest contributor: <strong className="text-ink">{top.key}</strong> at {usdK(top.component_var)} ({pct(top.share)} of VaR).{" "}
              <Link href="/breakdown">By position</Link>
            </p>
          )}
        </Card>
      </div>
    </>
  );
}
