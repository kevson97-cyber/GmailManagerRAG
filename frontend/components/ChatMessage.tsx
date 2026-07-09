"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import type { DisplayMessage } from "@/lib/useChat";

/** Friendly, present-progressive labels for tools.py's TOOL_SCHEMAS names. */
const TOOL_LABELS: Record<string, string> = {
  search_emails: "Searching emails",
  get_emails_by_sender: "Looking up emails by sender",
  get_emails_by_label: "Looking up emails by label",
  get_inbox_stats: "Checking inbox stats",
  get_top_senders: "Ranking senders",
  count_emails: "Counting emails",
  list_labels: "Listing labels",
  summarize_sender: "Gathering emails to summarize",
  trash_emails: "Preparing trash action",
  create_label: "Preparing new label",
  apply_label: "Preparing label action",
  create_filter: "Preparing filter",
};

export function humanizeToolName(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, " ");
}

// Hand-rolled prose classes (no @tailwindcss/typography) — keep every block
// element narrow-viewport safe: wrapped text, horizontally-scrollable code.
const markdownComponents: Components = {
  a: ({ children, ...props }) => (
    <a
      {...props}
      target="_blank"
      rel="noopener noreferrer"
      className="text-indigo-400 underline underline-offset-2 hover:text-indigo-300"
    >
      {children}
    </a>
  ),
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-slate-100">{children}</strong>,
  h1: ({ children }) => (
    <h3 className="mb-1.5 mt-2 text-base font-semibold text-slate-100 first:mt-0">{children}</h3>
  ),
  h2: ({ children }) => (
    <h3 className="mb-1.5 mt-2 text-base font-semibold text-slate-100 first:mt-0">{children}</h3>
  ),
  h3: ({ children }) => (
    <h4 className="mb-1 mt-2 text-sm font-semibold text-slate-100 first:mt-0">{children}</h4>
  ),
  blockquote: ({ children }) => (
    <blockquote className="mb-2 border-l-2 border-slate-700 pl-3 text-slate-400 last:mb-0">
      {children}
    </blockquote>
  ),
  code: ({ className, children, ...props }) => {
    const isFenced = typeof className === "string" && className.startsWith("language-");
    if (isFenced) {
      return (
        <code className={`font-mono text-xs ${className}`} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-[0.8em] text-slate-200" {...props}>
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre className="mb-2 overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs last:mb-0">
      {children}
    </pre>
  ),
};

function ToolCheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} className="h-2.5 w-2.5" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
    </svg>
  );
}

export default function ChatMessage({ message }: { message: DisplayMessage }) {
  switch (message.kind) {
    case "user":
      return (
        <div className="flex justify-end">
          <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-indigo-500 px-4 py-2.5 text-sm text-white">
            {message.text}
          </div>
        </div>
      );

    case "assistant":
      return (
        <div className="flex justify-start">
          <div className="max-w-[90%] rounded-2xl rounded-bl-sm border border-slate-800 bg-slate-900/60 px-4 py-2.5 text-sm text-slate-100">
            <div className="break-words">
              {message.text && <ReactMarkdown components={markdownComponents}>{message.text}</ReactMarkdown>}
              {message.streaming && (
                <span
                  className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-indigo-400 align-text-bottom"
                  aria-hidden="true"
                />
              )}
            </div>
          </div>
        </div>
      );

    case "tool":
      return (
        <div className="flex justify-start">
          <div
            className={`flex max-w-[90%] items-center gap-2 rounded-full border px-3 py-1.5 text-xs ${
              message.status === "running"
                ? "border-slate-700 bg-slate-900/60 text-slate-300"
                : "border-slate-800 bg-slate-900/30 text-slate-400"
            }`}
          >
            {message.status === "running" ? (
              <span
                className="h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-slate-600 border-t-indigo-400"
                aria-hidden="true"
              />
            ) : (
              <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400">
                <ToolCheckIcon />
              </span>
            )}
            <span className="truncate">
              {humanizeToolName(message.name)}
              {message.status === "running" && "…"}
              {message.status === "done" && message.summary && (
                <span className="text-slate-500"> — {message.summary}</span>
              )}
            </span>
          </div>
        </div>
      );

    case "error":
      return (
        <div className="flex justify-start">
          <div className="max-w-[90%] rounded-xl border border-red-900/50 bg-red-950/30 px-4 py-2.5 text-sm text-red-300">
            {message.text}
          </div>
        </div>
      );

    default:
      // "confirm" messages are rendered by ConfirmActionCard from the page's
      // message loop, not through this component.
      return null;
  }
}
