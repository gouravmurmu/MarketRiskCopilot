"use client";

import clsx from "clsx";
import { CircleCheck, FilePenLine, ShieldCheck, Sparkles, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Markdown } from "@/components/markdown";
import { Card, PageHeader, Skeleton, StatusPill } from "@/components/ui";
import { apiPost, useApi } from "@/lib/api";
import { demoCommentary, demoCommentaryDates } from "@/lib/demo";
import { longDate, shortDate } from "@/lib/format";
import type { Commentary, CommentaryDates } from "@/lib/types";

const STATUS_LABEL: Record<Commentary["status"], string> = {
  draft: "Validated draft",
  needs_review: "Needs review",
  approved: "Approved",
};
const statusTone = (s: Commentary["status"]) => (s === "approved" ? "ok" : s === "needs_review" ? "warning" : "info");

export default function CommentaryPage() {
  const [asOf, setAsOf] = useState<string | null>(null);
  const path = asOf ? `/commentary?as_of=${asOf}` : "/commentary";
  const { data, demo, loading } = useApi<Commentary>(path, demoCommentary);
  const dates = useApi<CommentaryDates>("/commentary/dates", demoCommentaryDates).data;

  const [saved, setSaved] = useState<Commentary | null>(null);
  const note = saved && saved.as_of === data?.as_of ? saved : data;
  const [tab, setTab] = useState<"preview" | "edit">("preview");
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [state, setState] = useState<{ kind: "idle" | "saving" | "error" | "done"; msg?: string }>({ kind: "idle" });

  useEffect(() => {
    setText(note?.final_md ?? note?.draft_md ?? "");
    setTab("preview");
    setState({ kind: "idle" });
  }, [note?.as_of, note?.final_md, note?.draft_md]);

  async function approve() {
    if (!note) return;
    setState({ kind: "saving" });
    const body = { as_of: note.as_of, final_md: text, approved_by: name.trim() };
    if (demo) {
      setSaved({ ...note, status: "approved", final_md: text, approved_by: body.approved_by, approved_at: new Date().toISOString() });
      setState({ kind: "done", msg: "Approved locally. In demo mode nothing is saved." });
      return;
    }
    try {
      setSaved(await apiPost<Commentary>("/commentary/approve", body));
      setState({ kind: "done", msg: "Approved and published." });
    } catch (e) {
      setState({ kind: "error", msg: (e as Error).message.startsWith("401") ? "Approval needs the approver token." : "Could not save. Try again." });
    }
  }

  const report = note?.validator_report;
  const edited = note ? text !== (note.final_md ?? note.draft_md ?? "") : false;

  return (
    <>
      <PageHeader eyebrow="Daily risk note" title="Commentary and sign-off" demo={demo} />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card
          title={note ? `Note for ${longDate(note.as_of)}` : "Note"}
          subtitle="Drafted by the copilot from engine tools, laid out in code, published only after sign-off"
          action={note && <StatusPill status={statusTone(note.status)} label={STATUS_LABEL[note.status]} />}
        >
          {loading && <Skeleton className="h-96" />}
          {!loading && !note && (
            <div className="flex items-center gap-4 py-6">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-apricot-100 text-apricot-700">
                <Sparkles aria-hidden="true" />
              </span>
              <p className="text-sm text-ink-2">No commentary yet. It is drafted after each end-of-day run once the copilot is switched on.</p>
            </div>
          )}
          {note && (
            <>
              <div role="tablist" aria-label="View" className="mb-4 inline-flex rounded-full bg-sage-50 p-1">
                {(["preview", "edit"] as const).map((t) => (
                  <button
                    key={t}
                    role="tab"
                    aria-selected={tab === t}
                    onClick={() => setTab(t)}
                    className={clsx("pill capitalize", tab === t ? "bg-white text-sage-700 shadow-sm" : "text-ink-muted hover:text-ink")}
                  >
                    {t === "edit" && <FilePenLine size={14} className="mr-1.5" aria-hidden="true" />}
                    {t}
                  </button>
                ))}
              </div>
              {tab === "preview" ? (
                text ? (
                  <Markdown>{text}</Markdown>
                ) : (
                  <p className="text-sm text-ink-muted">The draft did not pass validation. Write the note in the Edit tab.</p>
                )
              ) : (
                <>
                  <label htmlFor="note-md" className="sr-only">
                    Commentary markdown
                  </label>
                  <textarea
                    id="note-md"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    className="h-[480px] w-full rounded-2xl border border-line bg-canvas p-4 font-mono text-[13px] leading-relaxed outline-none focus:border-sage-400"
                  />
                </>
              )}

              <div className="mt-5 flex flex-col gap-3 border-t border-line pt-5 sm:flex-row sm:items-end">
                {note.status === "approved" && !edited ? (
                  <p className="inline-flex items-center gap-2 text-sm font-semibold text-sage-700">
                    <CircleCheck size={18} aria-hidden="true" />
                    Approved by {note.approved_by}
                    {note.approved_at && ` on ${longDate(note.approved_at.slice(0, 10))}`}
                  </p>
                ) : (
                  <>
                    <div className="flex-1">
                      <label htmlFor="approver" className="text-xs font-semibold text-ink-muted">
                        Approver
                      </label>
                      <input
                        id="approver"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Your name"
                        className="mt-1 h-11 w-full rounded-xl border border-line px-3 text-sm outline-none focus:border-sage-400"
                      />
                    </div>
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={name.trim().length < 2 || text.trim().length < 20 || state.kind === "saving"}
                      onClick={approve}
                    >
                      <ShieldCheck size={18} aria-hidden="true" />
                      {edited ? "Approve with edits" : "Approve"}
                    </button>
                  </>
                )}
              </div>
              {state.msg && (
                <p className={clsx("mt-2 text-sm", state.kind === "error" ? "text-coral-700" : "text-sage-700")} role="status">
                  {state.msg}
                </p>
              )}
            </>
          )}
        </Card>

        <div className="flex flex-col gap-5">
          <Card title="Validator" subtitle="Every figure is traced back to a tool output">
            {report ? (
              <div className="space-y-3 text-sm">
                <p className={clsx("inline-flex items-center gap-2 font-semibold", report.ok ? "text-sage-700" : "text-apricot-700")}>
                  {report.ok ? <CircleCheck size={18} aria-hidden="true" /> : <TriangleAlert size={18} aria-hidden="true" />}
                  {report.ok ? "All figures matched" : `${report.errors.length} issue${report.errors.length === 1 ? "" : "s"} left after retries`}
                </p>
                <dl className="grid grid-cols-2 gap-y-1.5 text-ink-2">
                  <dt className="text-ink-muted">Status</dt>
                  <dd>{note && STATUS_LABEL[note.status]}</dd>
                  <dt className="text-ink-muted">Attempts</dt>
                  <dd className="num">{report.attempts} of 3</dd>
                  <dt className="text-ink-muted">Model</dt>
                  <dd className="font-mono text-xs leading-5">{report.model}</dd>
                </dl>
                {report.errors.length > 0 && (
                  <ul className="space-y-1.5 rounded-xl bg-apricot-100/60 p-3 text-[13px] text-apricot-700">
                    {report.errors.map((e) => (
                      <li key={e}>{e}</li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <p className="text-sm text-ink-muted">No validator report.</p>
            )}
          </Card>

          <Card title="Recent notes">
            <ul className="divide-y divide-line">
              {(dates?.items ?? []).map((d) => (
                <li key={d.as_of}>
                  <button
                    type="button"
                    onClick={() => setAsOf(d.as_of)}
                    aria-current={note?.as_of === d.as_of ? "true" : undefined}
                    className={clsx(
                      "flex w-full items-center justify-between rounded-xl px-2 py-2.5 text-left text-sm transition hover:bg-sage-50",
                      note?.as_of === d.as_of && "bg-sage-50 font-semibold",
                    )}
                  >
                    <span>{shortDate(d.as_of)}</span>
                    <StatusPill status={statusTone(d.status)} label={STATUS_LABEL[d.status]} />
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
