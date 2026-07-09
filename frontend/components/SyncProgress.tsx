"use client";

import { useEffect, useRef, useState } from "react";
import { apiFetch, apiStream, ApiError } from "@/lib/api";
import { SYNC_TERMINAL_PHASES, type SyncProgressEvent } from "@/lib/types";

interface Props {
  /** Bump this to (re)open a fresh subscription — e.g. right after starting a sync. */
  streamKey: number;
  /** Called once per stream when a terminal event (done/error/cancelled) arrives. */
  onSyncFinished: () => void;
}

const PHASE_LABELS: Record<string, string> = {
  idle: "No sync has run yet",
  listing: "Listing messages…",
  fetching: "Fetching emails…",
  embedding: "Embedding & indexing…",
  done: "Done",
  error: "Error",
  cancelled: "Cancelled",
};

export default function SyncProgress({ streamKey, onSyncFinished }: Props) {
  const [event, setEvent] = useState<SyncProgressEvent | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const finishedRef = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    // Reset local state before (re)subscribing to the SSE stream, an external system.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setStreamError(null);
    setEvent(null);
    finishedRef.current = false;

    apiStream(
      "/api/sync/progress",
      { method: "GET" },
      (name, data) => {
        if (name !== "progress") return;
        const evt = data as SyncProgressEvent;
        setEvent(evt);
        if (SYNC_TERMINAL_PHASES.has(evt.phase) && !finishedRef.current) {
          finishedRef.current = true;
          onSyncFinished();
        }
      },
      controller.signal
    ).catch((err) => {
      if (controller.signal.aborted) return;
      setStreamError(err instanceof ApiError ? err.detail : "Lost connection to the sync progress stream.");
    });

    return () => controller.abort();
    // onSyncFinished is a stable callback from the parent; only streamKey should re-trigger the subscription.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamKey]);

  async function handleCancel() {
    setCancelling(true);
    try {
      await apiFetch("/api/sync/cancel", { method: "POST" });
    } catch {
      // Best-effort — the progress stream reflects the actual outcome regardless.
    } finally {
      setCancelling(false);
    }
  }

  if (streamError) {
    return (
      <section className="rounded-xl border border-red-900/50 bg-red-950/30 p-4 text-sm text-red-300">
        {streamError}
      </section>
    );
  }

  if (!event || event.phase === "idle") {
    return (
      <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-400">
        {event?.message || "No sync has run yet."}
      </section>
    );
  }

  const running = !SYNC_TERMINAL_PHASES.has(event.phase);
  const pct =
    event.total > 0
      ? Math.min(100, Math.round(((event.fetched + event.embedded) / (event.total * 2)) * 100))
      : event.phase === "done"
        ? 100
        : 0;

  const barColor =
    event.phase === "error" ? "bg-red-500" : event.phase === "cancelled" ? "bg-amber-500" : "bg-indigo-500";

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          {PHASE_LABELS[event.phase] ?? event.phase}
        </h2>
        {running && (
          <button
            type="button"
            onClick={handleCancel}
            disabled={cancelling}
            className="min-h-11 shrink-0 rounded-lg border border-slate-700 px-3 text-sm font-medium text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            {cancelling ? "Cancelling…" : "Cancel"}
          </button>
        )}
      </div>

      <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full transition-[width] duration-300 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
        <span>
          Fetched: {event.fetched}/{event.total}
        </span>
        <span>
          Embedded: {event.embedded}/{event.total}
        </span>
        <span>Added: {event.added}</span>
      </div>

      {event.message && <p className="mt-2 text-sm text-slate-300">{event.message}</p>}

      {!running && (
        <p
          className={`mt-2 text-sm font-medium ${
            event.phase === "done"
              ? "text-emerald-400"
              : event.phase === "cancelled"
                ? "text-amber-400"
                : "text-red-400"
          }`}
        >
          {event.phase === "done" &&
            `Sync complete — ${event.added} new email${event.added === 1 ? "" : "s"} added.`}
          {event.phase === "cancelled" && "Sync cancelled."}
          {event.phase === "error" && "Sync failed."}
        </p>
      )}
    </section>
  );
}
