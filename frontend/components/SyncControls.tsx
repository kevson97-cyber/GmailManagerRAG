"use client";

import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { SyncStartRequest, SyncStartResponse } from "@/lib/types";

const CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: "primary", label: "Primary" },
  { value: "social", label: "Social" },
  { value: "promotions", label: "Promotions" },
  { value: "updates", label: "Updates" },
  { value: "forums", label: "Forums" },
];

interface Props {
  /** Called after a sync is (re-)started, or a 409 shows one is already running — either way the caller should (re)attach to the progress stream. */
  onSyncStarted: () => void;
}

export default function SyncControls({ onSyncStarted }: Props) {
  const [maxEmails, setMaxEmails] = useState(500);
  const [query, setQuery] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function toggleCategory(value: string) {
    setCategories((prev) => (prev.includes(value) ? prev.filter((c) => c !== value) : [...prev, value]));
  }

  async function handleStart() {
    setError(null);
    setNotice(null);
    setStarting(true);
    try {
      const body: SyncStartRequest = {
        max_emails: maxEmails > 0 ? maxEmails : 500,
        query: query.trim(),
        categories,
      };
      await apiFetch<SyncStartResponse>("/api/sync/start", {
        method: "POST",
        body: JSON.stringify(body),
      });
      onSyncStarted();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setNotice("A sync is already running — showing its progress below.");
        onSyncStarted();
      } else if (err instanceof ApiError && err.status === 400) {
        setError(err.detail || "Gmail is not connected. Connect Gmail above before syncing.");
      } else {
        setError(err instanceof ApiError ? err.detail : "Failed to start sync.");
      }
    } finally {
      setStarting(false);
    }
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Sync &amp; index</h2>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm text-slate-300">
          Max emails
          <input
            type="number"
            min={1}
            value={maxEmails}
            onChange={(e) => setMaxEmails(Number(e.target.value))}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm text-slate-300">
          Gmail query (optional)
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. newer_than:30d"
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
          />
        </label>
      </div>

      <div className="mt-3">
        <span className="mb-1.5 block text-sm text-slate-300">Categories</span>
        <div className="flex flex-wrap gap-2">
          {CATEGORY_OPTIONS.map((opt) => {
            const active = categories.includes(opt.value);
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => toggleCategory(opt.value)}
                aria-pressed={active}
                className={`min-h-11 rounded-full border px-3.5 text-sm font-medium transition-colors ${
                  active
                    ? "border-indigo-400 bg-indigo-500/20 text-indigo-200"
                    : "border-slate-700 text-slate-300 hover:bg-slate-800"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      <button
        type="button"
        onClick={handleStart}
        disabled={starting}
        className="mt-4 min-h-11 w-full rounded-lg bg-indigo-500 px-4 text-sm font-semibold text-white hover:bg-indigo-400 disabled:opacity-50 sm:w-auto"
      >
        {starting ? "Starting…" : "Start sync"}
      </button>

      {notice && <p className="mt-2 text-sm text-amber-400">{notice}</p>}
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
    </section>
  );
}
