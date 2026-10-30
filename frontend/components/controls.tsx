"use client";

import clsx from "clsx";
import { useSelection } from "./selection";

const QUICK = [
  { key: "hs_500", label: "Historical" },
  { key: "fhs_500", label: "Filtered HS" },
  { key: "pn_ewma", label: "EWMA normal" },
  { key: "mc_ewma", label: "Monte Carlo" },
];
export const ALL_MODELS: { key: string; label: string }[] = [
  { key: "hs_250", label: "Historical 250d" },
  { key: "hs_500", label: "Historical 500d" },
  { key: "hs_aw_500", label: "Age-weighted HS" },
  { key: "fhs_500", label: "Filtered HS (GARCH)" },
  { key: "pn_sample_500", label: "Normal, sample cov" },
  { key: "pn_ewma", label: "Normal, EWMA" },
  { key: "pt_ewma", label: "Student-t, EWMA" },
  { key: "mc_ewma", label: "Monte Carlo" },
  { key: "svar", label: "Stressed VaR" },
];
export const modelName = (key: string) => ALL_MODELS.find((m) => m.key === key)?.label ?? key;

function Segmented<T extends string | number>({ label, options, value, onChange }: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1 rounded-full border border-line bg-white p-1">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={clsx("pill", o.value === value ? "bg-sage-600 text-white" : "text-ink-2 hover:bg-sage-50")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ModelControls({ showAll = true, confidence = true }: { showAll?: boolean; confidence?: boolean }) {
  const sel = useSelection();
  const quick = QUICK.some((q) => q.key === sel.model);
  return (
    <>
      <Segmented
        label="Model"
        options={QUICK.map((q) => ({ value: q.key, label: q.label }))}
        value={quick ? sel.model : ("" as string)}
        onChange={sel.setModel}
      />
      {showAll && (
        <label className="flex items-center gap-2 rounded-full border border-line bg-white py-1 pl-4 pr-1 text-[13px] font-semibold text-ink-2">
          <span>All models</span>
          <select
            value={sel.model}
            onChange={(e) => sel.setModel(e.target.value)}
            className="min-h-9 rounded-full border-0 bg-sage-50 px-3 text-[13px] font-semibold text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-sage-600"
          >
            {ALL_MODELS.map((m) => (
              <option key={m.key} value={m.key}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {confidence && (
        <Segmented
          label="Confidence"
          options={[
            { value: 0.99, label: "99%" },
            { value: 0.975, label: "97.5%" },
          ]}
          value={sel.confidence}
          onChange={sel.setConfidence}
        />
      )}
    </>
  );
}
