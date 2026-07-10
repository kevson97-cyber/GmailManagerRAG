"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { GenericRoutineStatus } from "@/lib/types";

const POLL_WHILE_RUNNING_MS = 3_000;

/**
 * Status + manual trigger for the background "Generic" labeling routine.
 * The backend scans the inbox on a schedule and labels promotions,
 * newsletters, and other skippable mail; this card shows the last run and
 * lets the user fire a pass on demand.
 */
export default function RoutinesCard() {
  const [status, setStatus] = useState<GenericRoutineStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const pollTimer = useRef<number | null>(null);

  const refresh = useCallback(async (): Promise<GenericRoutineStatus | null> => {
    try {
      const s = await apiFetch<GenericRoutineStatus>("/api/routines/generic");
      setStatus(s);
      setLoadError(null);
      return s;
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.detail : "Failed to load routine status.");
      return null;
    }
  }, []);

  // Load on mount; poll every 3s while a run is in flight.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial fetch from an external system
    refresh();
    return () => {
      if (pollTimer.current !== null) window.clearInterval(pollTimer.current);
    };
  }, [refresh]);

  useEffect(() => {
    if (!status?.running) return;
    const id = window.setInterval(async () => {
      const s = await refresh();
      if (s && !s.running) window.clearInterval(id);
    }, POLL_WHILE_RUNNING_MS);
    pollTimer.current = id;
    return () => window.clearInterval(id);
  }, [status?.running, refresh]);

  async function handleRunNow() {
    setStarting(true);
    try {
      await apiFetch("/api/routines/generic/run", { method: "POST" });
      await refresh(); // flips running=true and starts the poll loop
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        await refresh(); // already running — just attach to it
      } else {
        setLoadError(err instanceof ApiError ? err.detail : "Failed to start the routine.");
      }
    } finally {
      setStarting(false);
    }
  }

  const last = status?.last_run ?? null;
  const lastSummary = last
    ? `Last run ${new Date(last.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} — scanned ${last.scanned}, labeled ${last.labeled}`
    : "Not run yet.";

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Routines</h2>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-100">Generic labeling</p>
          <p className="mt-0.5 text-xs text-slate-400">
            Labels promotions, newsletters, and other skippable mail —{" "}
            {status?.enabled
              ? `runs every ${status.interval_minutes} min while the server is up.`
              : "auto-run is disabled (ROUTINE_INTERVAL_MINUTES=0)."}
          </p>
        </div>
        <button
          type="button"
          onClick={handleRunNow}
          disabled={starting || Boolean(status?.running)}
          className="min-h-11 rounded-lg bg-indigo-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-400 disabled:opacity-50"
        >
          {status?.running ? "Running…" : "Run now"}
        </button>
      </div>

      <p className="mt-2 text-xs text-slate-500">{lastSummary}</p>
      {last && last.errors.length > 0 && (
        <p className="mt-1 text-xs text-red-400">{last.errors.join(" · ")}</p>
      )}
      {loadError && <p className="mt-1 text-xs text-red-400">{loadError}</p>}
    </section>
  );
}
