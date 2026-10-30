"use client";

import clsx from "clsx";
import { Sparkles } from "lucide-react";

export function Card({ title, subtitle, action, className, children }: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={clsx("card animate-rise min-w-0", className)}>
      {(title || action) && (
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <p className="subtle mt-0.5">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-xl bg-sage-50", className)} aria-hidden="true" />;
}

export function DemoBadge({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full bg-apricot-100 px-3 py-1 text-xs font-bold text-apricot-700"
      title="The API is not reachable yet, so this page shows sample numbers"
    >
      <Sparkles size={13} aria-hidden="true" /> Demo data
    </span>
  );
}

export function StatusPill({ status, label }: { status: string; label?: string }) {
  const style =
    status === "breach" || status === "red" || status === "critical"
      ? "bg-coral-100 text-coral-700"
      : status === "warning" || status === "yellow"
        ? "bg-apricot-100 text-apricot-700"
        : status === "info"
          ? "bg-sky-100 text-sky-700"
          : "bg-sage-100 text-sage-700";
  return <span className={clsx("rounded-full px-2.5 py-0.5 text-xs font-bold", !label && "capitalize", style)}>{label ?? status}</span>;
}

export function PageHeader({ eyebrow, title, demo, children }: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  demo?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          {eyebrow && <p className="text-sm font-medium text-ink-muted">{eyebrow}</p>}
          <DemoBadge show={!!demo} />
        </div>
        <h1 className="text-[26px] font-bold leading-tight tracking-tight sm:text-3xl">{title}</h1>
      </div>
      {children && <div className="flex flex-wrap gap-2.5">{children}</div>}
    </div>
  );
}
