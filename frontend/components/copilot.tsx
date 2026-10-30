"use client";

import clsx from "clsx";
import { ArrowUp, Check, LoaderCircle, Sparkles, Wrench, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Markdown } from "@/components/markdown";
import { apiConfigured, streamChat } from "@/lib/api";
import { demoChat } from "@/lib/demo";
import type { ChatEvent } from "@/lib/types";

type ToolChip = { id: string; name: string; state: "running" | "ok" | "error"; input: Record<string, unknown> };
type Turn = { role: "user" | "assistant"; content: string; tools?: ToolChip[]; demo?: boolean; error?: string };

const SUGGESTIONS = [
  "Why did VaR change today?",
  "Are any limits in warning or breach?",
  "What if we cut NVDA by half?",
  "Did we have a backtest exception recently?",
];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function Copilot() {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns]);
  useEffect(() => {
    if (open) inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const patchLast = (fn: (t: Turn) => Turn) =>
    setTurns((ts) => [...ts.slice(0, -1), fn(ts[ts.length - 1])]);

  const apply = (e: ChatEvent) => {
    if (e.type === "text") patchLast((t) => ({ ...t, content: t.content + e.text }));
    else if (e.type === "tool_call")
      patchLast((t) => ({ ...t, tools: [...(t.tools ?? []), { id: e.id, name: e.name, input: e.input, state: "running" }] }));
    else if (e.type === "tool_result")
      patchLast((t) => ({ ...t, tools: t.tools?.map((c) => (c.id === e.id ? { ...c, state: e.ok ? "ok" : "error" } : c)) }));
    else if (e.type === "error") patchLast((t) => ({ ...t, error: e.message }));
  };

  async function playDemo(q: string) {
    patchLast((t) => ({ ...t, demo: true }));
    for (const e of demoChat(q)) {
      await sleep(e.type === "tool_result" ? 450 : 150);
      if (e.type === "text") {
        for (const word of e.text.split(/(?<= )/)) {
          apply({ type: "text", text: word });
          await sleep(12);
        }
      } else apply(e);
    }
  }

  async function ask(q: string) {
    const question = q.trim();
    if (!question || busy) return;
    const history = turns.filter((t) => t.content && !t.error).map(({ role, content }) => ({ role, content }));
    setTurns((ts) => [...ts, { role: "user", content: question }, { role: "assistant", content: "", tools: [] }]);
    setInput("");
    setBusy(true);
    try {
      if (!apiConfigured) await playDemo(question);
      else {
        abort.current = new AbortController();
        try {
          await streamChat({ messages: [...history, { role: "user", content: question }] }, apply, abort.current.signal);
        } catch (err) {
          if ((err as Error).name === "AbortError") return;
          // API asleep, copilot disabled or over its daily limit: fall back to the scripted demo.
          await playDemo(question);
        }
      }
    } finally {
      setBusy(false);
      abort.current = null;
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={clsx(
          "fixed bottom-5 right-5 z-30 inline-flex min-h-12 items-center gap-2 rounded-full bg-sage-600 px-5 text-sm font-semibold text-white shadow-lg shadow-sage-600/25 transition hover:-translate-y-0.5 hover:bg-sage-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sage-600",
          open && "pointer-events-none opacity-0",
        )}
        aria-haspopup="dialog"
      >
        <Sparkles size={18} aria-hidden="true" /> Ask the copilot
      </button>

      <div
        className={clsx("fixed inset-0 z-40 bg-ink/10 backdrop-blur-[2px] transition-opacity", open ? "opacity-100" : "pointer-events-none opacity-0")}
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Risk copilot"
        className={clsx(
          "fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-white shadow-2xl transition-transform duration-300 sm:w-[440px] sm:rounded-l-[24px]",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-center gap-3 border-b border-line bg-sage-50 px-5 py-4 sm:rounded-tl-[24px]">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-sage-200 text-sage-600">
            <Sparkles size={18} aria-hidden="true" />
          </span>
          <div className="flex-1">
            <p className="font-bold leading-tight">Risk copilot</p>
            <p className="text-xs text-ink-muted">Answers only with figures from read-only engine tools</p>
          </div>
          <button type="button" onClick={() => setOpen(false)} className="rounded-full p-2 text-ink-muted hover:bg-sage-100" aria-label="Close copilot">
            <X size={20} />
          </button>
        </header>

        <div ref={scroller} className="flex-1 space-y-4 overflow-y-auto px-5 py-5" aria-live="polite">
          {turns.length === 0 && (
            <div className="animate-rise">
              <p className="text-sm text-ink-2">
                Ask about today&apos;s VaR, its drivers, limits, backtests or a hypothetical trade. Every figure comes from a tool call you can see.
              </p>
              <div className="mt-4 flex flex-col gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => ask(s)}
                    className="rounded-2xl border border-sage-300 bg-white px-4 py-3 text-left text-sm font-medium text-sage-700 transition hover:border-sage-400 hover:bg-sage-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {turns.map((t, i) =>
            t.role === "user" ? (
              <div key={i} className="ml-10 animate-rise rounded-2xl rounded-br-md bg-sage-600 px-4 py-2.5 text-sm text-white">
                {t.content}
              </div>
            ) : (
              <div key={i} className="mr-4 animate-rise">
                {t.tools && t.tools.length > 0 && (
                  <ul className="mb-2 flex flex-wrap gap-1.5" aria-label="Tools called">
                    {t.tools.map((c) => (
                      <li
                        key={c.id}
                        title={JSON.stringify(c.input)}
                        className={clsx(
                          "inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-mono text-[11px]",
                          c.state === "error" ? "bg-coral-100 text-coral-700" : "bg-sky-100 text-sky-700",
                        )}
                      >
                        {c.state === "running" ? (
                          <LoaderCircle size={12} className="animate-spin" aria-hidden="true" />
                        ) : c.state === "ok" ? (
                          <Check size={12} aria-hidden="true" />
                        ) : (
                          <Wrench size={12} aria-hidden="true" />
                        )}
                        {c.name}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="rounded-2xl rounded-bl-md border border-line bg-canvas px-4 py-3">
                  {t.content ? (
                    <Markdown compact>{t.content}</Markdown>
                  ) : t.error ? null : (
                    <span className="inline-flex items-center gap-2 text-sm text-ink-muted">
                      <LoaderCircle size={14} className="animate-spin" aria-hidden="true" /> Thinking
                    </span>
                  )}
                  {t.error && <p className="text-sm font-medium text-coral-700">{t.error}</p>}
                </div>
                {t.demo && <p className="mt-1 text-[11px] font-semibold text-apricot-700">Demo answer from sample data</p>}
              </div>
            ),
          )}
        </div>

        <form
          className="border-t border-line p-4"
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
        >
          <div className="flex items-end gap-2 rounded-2xl border border-sage-300 bg-white p-2 focus-within:border-sage-500">
            <label htmlFor="copilot-input" className="sr-only">
              Ask a question
            </label>
            <textarea
              id="copilot-input"
              ref={inputRef}
              rows={1}
              value={input}
              maxLength={2000}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  ask(input);
                }
              }}
              placeholder="Why did FX VaR jump?"
              className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-ink-muted"
            />
            <button type="submit" disabled={busy || !input.trim()} className="btn-primary min-h-10 w-10 px-0" aria-label="Send">
              {busy ? <LoaderCircle size={18} className="animate-spin" /> : <ArrowUp size={18} />}
            </button>
          </div>
          <p className="mt-2 text-[11px] text-ink-muted">What-if answers are hypothetical. Not investment advice.</p>
        </form>
      </aside>
    </>
  );
}
