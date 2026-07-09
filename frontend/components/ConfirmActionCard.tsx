"use client";

import type { ChatPreviewItem } from "@/lib/types";
import type { DisplayConfirmMessage } from "@/lib/useChat";

interface Props {
  message: DisplayConfirmMessage;
  /** True while the resume stream for THIS card's confirm_token is in flight. */
  resolving: boolean;
  onConfirm: () => void;
  onDecline: () => void;
}

function formatPreviewDate(date: string | undefined): string {
  if (!date) return "";
  const parsed = new Date(date);
  if (Number.isNaN(parsed.getTime())) return date;
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function PreviewRow({ item }: { item: ChatPreviewItem }) {
  const dateLabel = formatPreviewDate(item.date);
  return (
    <li className="rounded-md bg-amber-950/30 px-2.5 py-1.5 text-xs">
      <p className="truncate font-medium text-amber-100">{item.subject || "(no subject)"}</p>
      <p className="truncate text-amber-200/70">
        {item.sender || "unknown sender"}
        {dateLabel && ` · ${dateLabel}`}
      </p>
    </li>
  );
}

export default function ConfirmActionCard({ message, resolving, onConfirm, onDecline }: Props) {
  const pending = message.status === "pending";
  const preview = message.preview.slice(0, 10);

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[92%] rounded-xl border border-amber-800/60 bg-amber-950/20 p-4 sm:max-w-md">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm font-medium text-amber-200">{message.description || "Confirm this action"}</p>
          <span className="shrink-0 rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-semibold text-amber-200">
            {message.count}
          </span>
        </div>

        {preview.length > 0 && (
          <ul className="mt-3 max-h-48 space-y-1.5 overflow-y-auto rounded-lg border border-amber-900/40 bg-black/20 p-2">
            {preview.map((item, i) => (
              <PreviewRow key={item.id || i} item={item} />
            ))}
          </ul>
        )}

        {message.action === "trash_emails" && (
          <p className="mt-3 text-xs leading-relaxed text-amber-200/70">
            Trashed emails are recoverable from Gmail Trash for 30 days.
          </p>
        )}

        {pending ? (
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={onConfirm}
              className="min-h-11 flex-1 rounded-lg bg-red-600 px-3 text-sm font-semibold text-white hover:bg-red-500"
            >
              Confirm
            </button>
            <button
              type="button"
              onClick={onDecline}
              className="min-h-11 flex-1 rounded-lg border border-slate-700 px-3 text-sm font-medium text-slate-200 hover:bg-slate-800"
            >
              Cancel
            </button>
          </div>
        ) : (
          <div className="mt-4 flex min-h-11 items-center gap-2 text-sm font-medium">
            {resolving && (
              <span
                className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-slate-600 border-t-indigo-400"
                aria-hidden="true"
              />
            )}
            <span className={message.status === "confirmed" ? "text-emerald-400" : "text-slate-400"}>
              {message.status === "confirmed" ? "Confirmed" : "Declined"}
              {resolving ? "…" : ""}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
