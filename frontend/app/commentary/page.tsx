import { Sparkles } from "lucide-react";
import { Card, PageHeader } from "@/components/ui";

export default function Commentary() {
  return (
    <>
      <PageHeader eyebrow="Daily risk note" title="Commentary and sign-off" />
      <Card>
        <div className="flex flex-col items-start gap-3 py-6 sm:flex-row sm:items-center sm:gap-5">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-apricot-100 text-apricot-700">
            <Sparkles aria-hidden="true" />
          </span>
          <div>
            <p className="font-bold">The AI copilot arrives in the next build step</p>
            <p className="mt-1 max-w-2xl text-sm text-ink-2">
              It will draft the daily note from read-only engine tools, a validator will trace every figure back to an engine output, and the
              note is only published after an analyst edits and approves it here.
            </p>
          </div>
        </div>
      </Card>
    </>
  );
}
