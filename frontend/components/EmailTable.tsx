"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { EmailListResponse, EmailSortField, LabelOut, SortOrder, StatsResponse } from "@/lib/types";

const PAGE_SIZE = 50;

const SORT_OPTIONS: { value: EmailSortField; label: string }[] = [
  { value: "date", label: "Date" },
  { value: "sender", label: "Sender" },
  { value: "subject", label: "Subject" },
];

// Gmail's real category label IDs (what gmail_client.py stores in each row's
// "labels" array) — shown even when /api/gmail/labels can't be reached
// because Gmail isn't connected yet.
const SYSTEM_LABELS: LabelOut[] = [
  { id: "CATEGORY_PERSONAL", name: "Primary", type: "system" },
  { id: "CATEGORY_SOCIAL", name: "Social", type: "system" },
  { id: "CATEGORY_PROMOTIONS", name: "Promotions", type: "system" },
  { id: "CATEGORY_UPDATES", name: "Updates", type: "system" },
  { id: "CATEGORY_FORUMS", name: "Forums", type: "system" },
];

interface Props {
  /** Bump after a sync completes (or the index is cleared) to force a refetch. */
  refreshKey: number;
}

function formatDate(date: string): string {
  if (!date) return "—";
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function EmailTable({ refreshKey }: Props) {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [label, setLabel] = useState("");
  const [sender, setSender] = useState("");
  const [sort, setSort] = useState<EmailSortField>("date");
  const [order, setOrder] = useState<SortOrder>("desc");
  const [offset, setOffset] = useState(0);

  const [labels, setLabels] = useState<LabelOut[]>(SYSTEM_LABELS);
  const [result, setResult] = useState<EmailListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [clearStep, setClearStep] = useState<0 | 1>(0);
  const [clearing, setClearing] = useState(false);
  const [clearError, setClearError] = useState<string | null>(null);

  // Debounce free-text search 300ms before it drives a fetch.
  useEffect(() => {
    const id = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setOffset(0);
    }, 300);
    return () => window.clearTimeout(id);
  }, [searchInput]);

  // Any other filter/sort change resets to page 1 — bundled into the setters below
  // (rather than a separate effect) so changing one piece of state doesn't fan out
  // into a second render pass.
  function handleLabelChange(value: string) {
    setLabel(value);
    setOffset(0);
  }

  function handleSenderChange(value: string) {
    setSender(value);
    setOffset(0);
  }

  function handleSortChange(value: EmailSortField) {
    setSort(value);
    setOffset(0);
  }

  function handleOrderToggle() {
    setOrder((o) => (o === "asc" ? "desc" : "asc"));
    setOffset(0);
  }

  // Label options: merge Gmail's real labels with the system category list;
  // fall back to just the system categories if Gmail is disconnected (the
  // endpoint 400s) or the backend is otherwise unreachable.
  useEffect(() => {
    let cancelled = false;
    apiFetch<LabelOut[]>("/api/gmail/labels")
      .then((real) => {
        if (cancelled) return;
        const merged = [...SYSTEM_LABELS];
        for (const l of real) {
          if (!merged.some((m) => m.id === l.id)) merged.push(l);
        }
        setLabels(merged);
      })
      .catch(() => {
        if (!cancelled) setLabels(SYSTEM_LABELS);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  // Guards against out-of-order responses when filters change faster than
  // requests resolve: only the latest request may update state.
  const loadSeqRef = useRef(0);

  const loadEmails = useCallback(async () => {
    const seq = ++loadSeqRef.current;
    setLoading(true);
    setLoadError(null);
    try {
      const params = new URLSearchParams({
        search,
        label,
        sender,
        sort,
        order,
        offset: String(offset),
        limit: String(PAGE_SIZE),
      });
      const data = await apiFetch<EmailListResponse>(`/api/emails?${params.toString()}`);
      if (seq !== loadSeqRef.current) return;
      setResult(data);
    } catch (err) {
      if (seq !== loadSeqRef.current) return;
      setLoadError(err instanceof ApiError ? err.detail : "Failed to load emails.");
      setResult(null);
    } finally {
      if (seq === loadSeqRef.current) setLoading(false);
    }
  }, [search, label, sender, sort, order, offset]);

  useEffect(() => {
    // Data fetch on mount + whenever filters/pagination/refreshKey change.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadEmails();
  }, [loadEmails, refreshKey]);

  const loadStats = useCallback(async () => {
    try {
      setStats(await apiFetch<StatsResponse>("/api/stats"));
    } catch {
      setStats(null);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadStats();
  }, [loadStats, refreshKey]);

  async function handleClearIndex() {
    setClearing(true);
    setClearError(null);
    try {
      await apiFetch("/api/emails/index", { method: "DELETE" });
      setClearStep(0);
      setOffset(0);
      setExpandedId(null);
      await Promise.all([loadEmails(), loadStats()]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setClearError("Cannot clear the index while a sync is running.");
      } else {
        setClearError(err instanceof ApiError ? err.detail : "Failed to clear the index.");
      }
    } finally {
      setClearing(false);
    }
  }

  function labelName(id: string): string {
    return labels.find((l) => l.id === id)?.name ?? id;
  }

  const total = result?.total ?? 0;
  const items = result?.items ?? [];
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + PAGE_SIZE, total);
  const hasFilters = search !== "" || label !== "" || sender !== "";

  return (
    <section className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Indexed emails</h2>

      {/* Filters */}
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <input
          type="search"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search subject, sender, snippet…"
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500 lg:col-span-2"
        />
        <select
          value={label}
          onChange={(e) => handleLabelChange(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
        >
          <option value="">All labels</option>
          {labels.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={sender}
          onChange={(e) => handleSenderChange(e.target.value)}
          placeholder="Filter by sender…"
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-400">Sort</span>
        <select
          value={sort}
          onChange={(e) => handleSortChange(e.target.value as EmailSortField)}
          className="min-h-11 rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-slate-100 outline-none focus:border-indigo-500"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={handleOrderToggle}
          className="min-h-11 rounded-lg border border-slate-700 px-3 text-sm text-slate-200 hover:bg-slate-800"
          aria-label={`Sort order: ${order === "asc" ? "ascending" : "descending"}`}
        >
          {order === "asc" ? "↑ Ascending" : "↓ Descending"}
        </button>
      </div>

      {/* Results */}
      {loadError && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-3 text-sm text-red-300">
          {loadError}
          <button
            type="button"
            onClick={() => loadEmails()}
            className="ml-3 min-h-11 rounded-lg border border-red-800 px-3 text-sm font-medium text-red-200 hover:bg-red-900/40"
          >
            Retry
          </button>
        </div>
      )}

      {!loadError && loading && <p className="py-6 text-center text-sm text-slate-400">Loading…</p>}

      {!loadError && !loading && items.length === 0 && (
        <p className="py-6 text-center text-sm text-slate-400">
          {hasFilters ? "No emails match these filters." : "No emails indexed yet — run a sync above to get started."}
        </p>
      )}

      {!loadError && !loading && items.length > 0 && (
        <>
          {/* Desktop table */}
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[720px] table-fixed border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
                  <th className="w-2/5 py-2 pr-3 font-medium">Subject</th>
                  <th className="w-1/5 py-2 pr-3 font-medium">Sender</th>
                  <th className="w-1/5 py-2 pr-3 font-medium">Recipient</th>
                  <th className="w-24 py-2 pr-3 font-medium">Date</th>
                  <th className="py-2 font-medium">Labels</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <Fragment key={item.id}>
                    <tr
                      onClick={() => setExpandedId((cur) => (cur === item.id ? null : item.id))}
                      className="cursor-pointer border-b border-slate-800/60 align-top hover:bg-slate-800/40"
                    >
                      <td className="truncate py-2.5 pr-3 text-slate-200">{item.subject || "(no subject)"}</td>
                      <td className="truncate py-2.5 pr-3 text-slate-300">{item.sender || "—"}</td>
                      <td className="truncate py-2.5 pr-3 text-slate-400">{item.recipient || "—"}</td>
                      <td className="py-2.5 pr-3 text-slate-400">{formatDate(item.date)}</td>
                      <td className="py-2.5">
                        <div className="flex flex-wrap gap-1">
                          {item.labels.slice(0, 3).map((lid) => (
                            <span
                              key={lid}
                              className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-300"
                            >
                              {labelName(lid)}
                            </span>
                          ))}
                          {item.labels.length > 3 && (
                            <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
                              +{item.labels.length - 3}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                    {expandedId === item.id && (
                      <tr className="border-b border-slate-800/60 bg-slate-900/60">
                        <td colSpan={5} className="px-3 py-3 text-sm text-slate-300">
                          {item.snippet || "No preview available."}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="flex flex-col gap-2 md:hidden">
            {items.map((item) => (
              <div key={item.id} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                <p className="font-semibold text-slate-100">{item.subject || "(no subject)"}</p>
                <p className="mt-0.5 text-xs text-slate-400">
                  {item.sender || "—"} · {formatDate(item.date)}
                </p>
                {item.labels.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {item.labels.slice(0, 4).map((lid) => (
                      <span key={lid} className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                        {labelName(lid)}
                      </span>
                    ))}
                    {item.labels.length > 4 && (
                      <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
                        +{item.labels.length - 4}
                      </span>
                    )}
                  </div>
                )}
                {item.snippet && <p className="mt-1.5 line-clamp-2 text-sm text-slate-400">{item.snippet}</p>}
              </div>
            ))}
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between gap-3 pt-1 text-sm text-slate-400">
            <span>
              {rangeStart}–{rangeEnd} of {total}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                className="min-h-11 min-w-11 rounded-lg border border-slate-700 px-3 text-slate-200 hover:bg-slate-800 disabled:opacity-40"
              >
                Prev
              </button>
              <button
                type="button"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset((o) => o + PAGE_SIZE)}
                className="min-h-11 min-w-11 rounded-lg border border-slate-700 px-3 text-slate-200 hover:bg-slate-800 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}

      {/* Footer: stats + clear index */}
      <div className="flex flex-col gap-2 border-t border-slate-800 pt-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-slate-500">
          {stats
            ? `${stats.total_indexed} indexed · ${stats.unique_senders} unique senders`
            : "Stats unavailable"}
        </p>

        {clearStep === 0 ? (
          <button
            type="button"
            onClick={() => setClearStep(1)}
            className="min-h-11 self-start rounded-lg border border-red-900 px-3 text-sm font-medium text-red-300 hover:bg-red-950/40 sm:self-auto"
          >
            Clear index
          </button>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-red-300">
              Permanently remove all indexed emails from the local search index (Gmail itself is
              untouched)?
            </span>
            <button
              type="button"
              onClick={handleClearIndex}
              disabled={clearing}
              className="min-h-11 rounded-lg bg-red-600 px-3 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
            >
              {clearing ? "Clearing…" : "Yes, clear it"}
            </button>
            <button
              type="button"
              onClick={() => setClearStep(0)}
              className="min-h-11 rounded-lg border border-slate-700 px-3 text-sm text-slate-300 hover:bg-slate-800"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
      {clearError && <p className="text-sm text-red-400">{clearError}</p>}
    </section>
  );
}
