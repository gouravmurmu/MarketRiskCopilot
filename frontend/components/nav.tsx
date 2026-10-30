"use client";

import clsx from "clsx";
import { CircleCheck, Leaf, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApi } from "@/lib/api";
import { demoDataQuality } from "@/lib/demo";
import { longDate } from "@/lib/format";
import type { DataQuality } from "@/lib/types";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/breakdown", label: "Risk breakdown" },
  { href: "/attribution", label: "VaR change" },
  { href: "/backtests", label: "Backtests" },
  { href: "/whatif", label: "What-if" },
  { href: "/commentary", label: "Commentary" },
  { href: "/data-quality", label: "Data quality" },
];

export function Nav() {
  const path = usePathname();
  const dq = useApi<DataQuality>("/data-quality", demoDataQuality).data;
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-[1360px] flex-wrap items-center gap-x-8 gap-y-3 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5 font-bold tracking-tight text-ink">
          <span className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-sage-200 text-sage-600">
            <Leaf size={20} aria-hidden="true" />
          </span>
          <span className="text-[17px]">Risk Copilot</span>
        </Link>
        <nav aria-label="Main" className="-mx-1 order-3 flex w-full gap-1 overflow-x-auto px-1 pb-1 lg:order-none lg:w-auto lg:flex-1 lg:pb-0">
          {LINKS.map((l) => {
            const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={clsx(
                  "whitespace-nowrap rounded-full px-3.5 py-2.5 text-sm transition-colors",
                  active ? "bg-sage-100 font-semibold text-sage-700" : "text-ink-muted hover:bg-sage-50 hover:text-ink",
                )}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        {dq && (
          <div className="ml-auto flex flex-wrap items-center gap-2 lg:ml-0">
            {dq.blocking ? (
              <Link href="/data-quality" className="inline-flex items-center gap-1.5 rounded-full bg-coral-100 px-3 py-1.5 text-[13px] font-semibold text-coral-700">
                <TriangleAlert size={14} aria-hidden="true" /> Run blocked
              </Link>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-sage-100 px-3 py-1.5 text-[13px] font-semibold text-sage-700">
                <CircleCheck size={14} aria-hidden="true" /> Data checks passed
              </span>
            )}
            <span className="rounded-full border border-line bg-canvas px-3 py-1.5 text-[13px] text-ink-2">As of {longDate(dq.as_of)}</span>
          </div>
        )}
      </div>
    </header>
  );
}
