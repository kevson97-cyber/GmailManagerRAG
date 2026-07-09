"use client";

import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { getApiToken, getApiUrl, setApiToken, setApiUrl } from "@/lib/settings";
import type { StatusResponse } from "@/lib/types";
import { CloseIcon } from "./icons";

interface Props {
  open: boolean;
  onClose: () => void;
}

type TestState =
  | { kind: "idle" }
  | { kind: "testing" }
  | { kind: "ok"; detail: string }
  | { kind: "error"; detail: string };

export default function SettingsSheet({ open, onClose }: Props) {
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [test, setTest] = useState<TestState>({ kind: "idle" });
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Re-hydrate from localStorage every time the sheet is opened.
  useEffect(() => {
    if (!open) return;
    // Re-hydrate from localStorage (an external system) each time the sheet opens.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUrl(getApiUrl());
    setToken(getApiToken());
    setTest({ kind: "idle" });
    setSavedAt(null);
  }, [open]);

  if (!open) return null;

  function persist() {
    setApiUrl(url.trim() || "http://localhost:8000");
    setApiToken(token.trim());
  }

  function handleSave() {
    persist();
    setSavedAt(Date.now());
  }

  async function handleTest() {
    persist();
    setTest({ kind: "testing" });

    try {
      await apiFetch("/api/health");
    } catch (err) {
      setTest({
        kind: "error",
        detail: err instanceof ApiError ? err.detail : "Backend unreachable.",
      });
      return;
    }

    try {
      const status = await apiFetch<StatusResponse>("/api/status");
      const gmail = status.gmail.connected ? status.gmail.email || "connected" : "not connected";
      const ollama = status.ollama.available ? status.ollama.model : "unavailable";
      setTest({
        kind: "ok",
        detail: `Backend reachable. Gmail: ${gmail} · Ollama: ${ollama} · Index: ${status.index.count} emails.`,
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setTest({ kind: "error", detail: "Backend reachable, but the API token was rejected. Check the token." });
      } else {
        setTest({ kind: "error", detail: err instanceof ApiError ? err.detail : "Request failed." });
      }
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        className="flex h-full w-full max-w-sm flex-col gap-4 overflow-y-auto border-l border-slate-800 bg-slate-900 p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-100">Settings</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close settings"
            className="flex h-11 w-11 items-center justify-center rounded-full text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          >
            <CloseIcon />
          </button>
        </div>

        <label className="flex flex-col gap-1 text-sm text-slate-300">
          Backend URL
          <input
            type="url"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="http://localhost:8000"
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm text-slate-300">
          API token
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste the token from backend/.env"
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
          />
        </label>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleSave}
            className="min-h-11 flex-1 rounded-lg bg-indigo-500 px-3 py-2.5 text-sm font-semibold text-white hover:bg-indigo-400"
          >
            Save
          </button>
          <button
            type="button"
            onClick={handleTest}
            disabled={test.kind === "testing"}
            className="min-h-11 flex-1 rounded-lg border border-slate-700 px-3 py-2.5 text-sm font-medium text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            {test.kind === "testing" ? "Testing…" : "Test connection"}
          </button>
        </div>

        {savedAt !== null && <p className="text-sm text-emerald-400">Saved.</p>}
        {test.kind === "ok" && <p className="text-sm text-emerald-400">{test.detail}</p>}
        {test.kind === "error" && <p className="text-sm text-red-400">{test.detail}</p>}

        <p className="mt-auto text-xs leading-relaxed text-slate-500">
          Stored only in this browser (localStorage) and takes priority over the
          NEXT_PUBLIC_API_URL / NEXT_PUBLIC_API_TOKEN values baked into the build — useful for
          pointing a deployed frontend at a fresh Cloudflare quick-tunnel URL without redeploying.
          Prefer entering the token here per-device rather than baking it into a public build.
        </p>
      </div>
    </div>
  );
}
