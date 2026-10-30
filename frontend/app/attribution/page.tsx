"use client";

import { Waterfall, effectNote } from "@/components/charts";
import { ModelControls, modelName } from "@/components/controls";
import { useSelection } from "@/components/selection";
import { Card, PageHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { demoAttribution } from "@/lib/demo";
import { EFFECT_LABEL, longDate, signedK, usdK } from "@/lib/format";
import type { Attribution } from "@/lib/types";

export default function VarChange() {
  const { model, confidence } = useSelection();
  const attr = useApi<Attribution>(`/risk/attribution?model=${model}&confidence=${confidence}`, () => demoAttribution(model, confidence));
  const a = attr.data;
  const roll = a?.effects.find((e) => e.effect === "window_roll");
  const vol = a?.effects.find((e) => e.effect === "volatility");
  const posEff = a?.effects.find((e) => e.effect === "position");

  return (
    <>
      <PageHeader eyebrow={a ? `${longDate(a.as_of)} · ${modelName(model)}` : undefined} title="What moved VaR today" demo={attr.demo}>
        <ModelControls />
      </PageHeader>

      <Card
        title={a && a.previous_var_usd != null ? `${usdK(a.previous_var_usd)} → ${usdK(a.var_usd)} (${signedK(a.var_usd - a.previous_var_usd)})` : "Waterfall"}
        subtitle="Computed deterministically by the engine: position first, then market data"
      >
        {a && a.previous_var_usd != null ? (
          <Waterfall key={`${model}-${confidence}`} previous={a.previous_var_usd} current={a.var_usd} effects={a.effects} height={260} />
        ) : (
          <Skeleton className="h-[320px]" />
        )}
      </Card>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-5">
        {a?.effects.map((e) => (
          <Card key={e.effect} title={`${EFFECT_LABEL[e.effect] ?? e.effect} ${signedK(e.amount_usd)}`}>
            <p className="text-sm text-ink-2">{effectNote(e)}</p>
          </Card>
        ))}
      </div>

      <div className="flex flex-wrap gap-5">
        {posEff && Object.keys(posEff.detail.changes ?? {}).length > 0 && (
          <Card className="flex-[1_1_320px]" title="Position changes">
            <ul className="flex flex-col gap-2 text-sm">
              {Object.entries(posEff.detail.changes ?? {}).map(([t, c]) => (
                <li key={t} className="flex justify-between rounded-xl bg-canvas px-3.5 py-2.5">
                  <span className="font-semibold">{t}</span>
                  <span className="num text-ink-2">{usdK(c.from, 0)} → {usdK(c.to, 0)}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}
        {roll && (
          <Card className="flex-[1_1_320px]" title="Scenarios that rolled" subtitle="P&L of each scenario on today's positions">
            <ul className="flex flex-col gap-2 text-sm">
              {[...(roll.detail.dropped ?? []).map((s) => ({ ...s, kind: "Dropped out" })), ...(roll.detail.added ?? []).map((s) => ({ ...s, kind: "Entered" }))].map((s) => (
                <li key={s.kind + s.date} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-canvas px-3.5 py-2.5">
                  <span><span className="font-semibold">{s.kind}</span> · {longDate(s.date)}</span>
                  <span className="num text-ink-2">
                    {usdK(s.pnl)}
                    {s.in_tail && <span className="ml-2 rounded-full bg-apricot-100 px-2 py-px text-xs font-bold text-apricot-700">in tail</span>}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}
        {vol && (
          <Card className="flex-[1_1_320px]" title="Daily volatility moves" subtitle="Today vs yesterday, largest first">
            <ul className="flex flex-col gap-2 text-sm">
              {Object.entries(vol.detail.daily_vol ?? {})
                .sort((x, y) => Math.abs(y[1].to / y[1].from - 1) - Math.abs(x[1].to / x[1].from - 1))
                .slice(0, 6)
                .map(([t, v]) => (
                  <li key={t} className="flex justify-between rounded-xl bg-canvas px-3.5 py-2.5">
                    <span className="font-semibold">{t}</span>
                    <span className="num text-ink-2">
                      {(v.from * 100).toFixed(2)}% → {(v.to * 100).toFixed(2)}%
                    </span>
                  </li>
                ))}
            </ul>
          </Card>
        )}
      </div>
    </>
  );
}
