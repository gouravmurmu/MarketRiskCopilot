import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Markdown in the house style: sage headings, tidy tables, tabular numbers. */
export function Markdown({ children, compact = false }: { children: string; compact?: boolean }) {
  return (
    <div className={compact ? "md md-compact" : "md"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}
