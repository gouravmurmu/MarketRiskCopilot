"use client";

import { CircleCheck, TriangleAlert } from "lucide-react";
import { Card, PageHeader, Skeleton, StatusPill } from "@/components/ui";
import { useApi } from "@/lib/api";
import { demoDataQuality } from "@/lib/demo";
import { longDate } from "@/lib/format";
import type { DataQuality } from "@/lib/types";

const CHECKS = [
  ["Missing prices", "Every instrument has a price on the as-of date"],
  ["Stale prices", "Flags a price unchanged for 3 or more days"],
  ["Return jumps", "Holds any move beyond 6 standard deviations for review"],
  ["Coverage", "Latest real print within 3 business days"],
  ["Forward fills", "Records every holiday fill instead of hiding it"],
];

export default function DataQualityPage() {
  const dq = useApi<DataQuality>("/data-quality", demoDataQuality);
  const d = dq.data;
  const open = d?.issues.filter((i) => !i.resolved) ?? [];
  return (
    <>
      <PageHeader eyebrow={d ? longDate(d.as_of) : undefined} title="Data quality" demo={dq.demo} />
      {d ? (
        <div className={`card flex items-center gap-4 ${d.blocking ? "!border-coral-400 !bg-coral-100" : "!bg-sage-100"}`}>
          {d.blocking ? <TriangleAlert className="shrink-0 text-coral-700" aria-hidden="true" /> : <CircleCheck className="shrink-0 text-sage-700" aria-hidden="true" />}
          <div>
            <p className="font-bold">{d.blocking ? "Risk run blocked" : "All checks passed, risk run completed"}</p>
            <p className="text-sm text-ink-2">
              {d.blocking ? "A critical issue on the as-of date stopped the engine before any number was produced. Resolve it to rerun." : `${open.length} informational note${open.length === 1 ? "" : "s"} below.`}
            </p>
          </div>
        </div>
      ) : (
        <Skeleton className="h-20" />
      )}
      <div className="flex flex-wrap gap-5">
        <Card className="flex-[2_1_420px]" title="Today's issues">
          {d && open.length === 0 && <p className="subtle">No issues.</p>}
          <ul className="flex flex-col gap-2">
            {open.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-3 rounded-xl bg-canvas px-4 py-3 text-sm">
                <StatusPill status={i.severity} />
                <span className="font-semibold">{i.ticker ?? "All"}</span>
                <span className="text-ink-2">{i.check}</span>
                <span className="flex-1 text-ink-muted">{i.detail}</span>
              </li>
            ))}
          </ul>
          <h3 className="mb-2 mt-6 text-sm font-bold">Checks that run before every risk run</h3>
          <ul className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-2">
            {CHECKS.map(([t, s]) => (
              <li key={t} className="rounded-xl border border-line px-3.5 py-3 text-sm">
                <div className="font-semibold">{t}</div>
                <div className="text-ink-muted">{s}</div>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="flex-[1_1_280px]" title="Latest real price" subtitle="Excludes forward fills">
          <ul className="flex flex-col gap-1.5 text-sm">
            {Object.entries(d?.latest_price_dates ?? {}).map(([t, date]) => (
              <li key={t} className="flex justify-between rounded-lg px-2 py-1.5 hover:bg-canvas">
                <span className="font-semibold">{t}</span>
                <span className={date === d?.as_of ? "text-ink-2" : "font-semibold text-apricot-700"}>{longDate(date)}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
