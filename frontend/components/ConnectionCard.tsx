"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { getApiUrl } from "@/lib/settings";
import type { ConnectResponse, StatusResponse } from "@/lib/types";

const POLL_INTERVAL_MS = 15_000;
const AUTH_POLL_INTERVAL_MS = 3_000;
const AUTH_POLL_TIMEOUT_MS = 5 * 60_000;

type LoadState =
  | { kind: "loading" }
  | { kind: "unreachable"; detail: string }
  | { kind: "unauthorized" }
  | { kind: "ready"; status: StatusResponse };

export default function ConnectionCard() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [awaitingDesktopAuth, setAwaitingDesktopAuth] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const authPollDeadline = useRef<number | null>(null);

  const refresh = useCallback(async (): Promise<StatusResponse | null> => {
    try {
      const status = await apiFetch<StatusResponse>("/api/status");
      setState({ kind: "ready", status });
      return status;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setState({ kind: "unauthorized" });
      } else {
        setState({
          kind: "unreachable",
          detail: err instanceof ApiError ? err.detail : "Backend unreachable.",
        });
      }
      return null;
    }
  }, []);

  useEffect(() => {
    // Fetch on mount, then poll — the canonical "synchronize with an external system" effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
    const id = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  // Fast poll while waiting on the PC-side Google consent browser window.
  useEffect(() => {
    if (!awaitingDesktopAuth) return;
    authPollDeadline.current = Date.now() + AUTH_POLL_TIMEOUT_MS;

    const id = window.setInterval(async () => {
      const status = await refresh();
      if (status?.gmail.connected) {
        setAwaitingDesktopAuth(false);
        return;
      }
      if (authPollDeadline.current !== null && Date.now() > authPollDeadline.current) {
        setAwaitingDesktopAuth(false);
        setActionError(
          "Timed out waiting for sign-in. Finish the Google consent flow on the PC, then click Connect Gmail again."
        );
      }
    }, AUTH_POLL_INTERVAL_MS);

    return () => window.clearInterval(id);
  }, [awaitingDesktopAuth, refresh]);

  async function handleConnect() {
    setActionError(null);
    setConnecting(true);
    try {
      const res = await apiFetch<ConnectResponse>("/api/gmail/connect", { method: "POST" });
      if (res.needs_desktop_auth) {
        setAwaitingDesktopAuth(true);
      } else {
        await refresh();
      }
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : "Failed to start the Gmail connection.");
    } finally {
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    setActionError(null);
    setDisconnecting(true);
    try {
      await apiFetch<ConnectResponse>("/api/gmail/disconnect", { method: "POST" });
      setConfirmDisconnect(false);
      await refresh();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : "Failed to disconnect Gmail.");
    } finally {
      setDisconnecting(false);
    }
  }

  if (state.kind === "loading") {
    return (
      <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-400">
        Checking backend…
      </section>
    );
  }

  if (state.kind === "unreachable") {
    return (
      <section className="rounded-xl border border-red-900/50 bg-red-950/30 p-4">
        <p className="text-sm font-medium text-red-300">Backend unreachable</p>
        <p className="mt-1 text-sm text-red-300/80">{state.detail}</p>
        <p className="mt-1 text-xs text-red-300/60">Currently pointed at {getApiUrl()} — check Settings.</p>
        <button
          type="button"
          onClick={() => refresh()}
          className="mt-3 min-h-11 rounded-lg border border-red-800 px-3 text-sm font-medium text-red-200 hover:bg-red-900/40"
        >
          Retry
        </button>
      </section>
    );
  }

  if (state.kind === "unauthorized") {
    return (
      <section className="rounded-xl border border-amber-900/50 bg-amber-950/30 p-4">
        <p className="text-sm font-medium text-amber-300">Unauthorized (401)</p>
        <p className="mt-1 text-sm text-amber-300/80">
          The backend rejected the API token. Open Settings and check the token matches
          backend/.env.
        </p>
        <button
          type="button"
          onClick={() => refresh()}
          className="mt-3 min-h-11 rounded-lg border border-amber-800 px-3 text-sm font-medium text-amber-200 hover:bg-amber-900/40"
        >
          Retry
        </button>
      </section>
    );
  }

  const { status } = state;

  return (
    <section className="flex flex-col gap-4 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      {/* Gmail */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-slate-200">Gmail</p>
          {status.gmail.connected ? (
            <p className="text-sm text-emerald-400">Connected as {status.gmail.email}</p>
          ) : (
            <p className="text-sm text-slate-400">Not connected</p>
          )}
        </div>
        <div className="flex gap-2">
          {status.gmail.connected ? (
            confirmDisconnect ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Disconnect Gmail?</span>
                <button
                  type="button"
                  onClick={handleDisconnect}
                  disabled={disconnecting}
                  className="min-h-11 rounded-lg bg-red-600 px-3 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
                >
                  {disconnecting ? "Disconnecting…" : "Confirm"}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmDisconnect(false)}
                  className="min-h-11 rounded-lg border border-slate-700 px-3 text-sm text-slate-300 hover:bg-slate-800"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmDisconnect(true)}
                className="min-h-11 rounded-lg border border-slate-700 px-3 text-sm font-medium text-slate-200 hover:bg-slate-800"
              >
                Disconnect
              </button>
            )
          ) : (
            <button
              type="button"
              onClick={handleConnect}
              disabled={connecting || awaitingDesktopAuth}
              className="min-h-11 rounded-lg bg-indigo-500 px-3 text-sm font-medium text-white hover:bg-indigo-400 disabled:opacity-50"
            >
              {connecting ? "Starting…" : awaitingDesktopAuth ? "Waiting for sign-in…" : "Connect Gmail"}
            </button>
          )}
        </div>
      </div>

      {awaitingDesktopAuth && (
        <div className="rounded-lg border border-indigo-800 bg-indigo-950/40 px-3 py-2.5 text-sm text-indigo-200">
          Finish Google sign-in in the browser window on your PC. This page will update
          automatically once you&apos;re connected.
        </div>
      )}

      {actionError && <p className="text-sm text-red-400">{actionError}</p>}

      {/* Ollama */}
      <div className="flex flex-col gap-1 border-t border-slate-800 pt-3">
        <p className="text-sm font-medium text-slate-200">Ollama</p>
        {status.ollama.available ? (
          <p className="text-sm text-emerald-400">Available — model {status.ollama.model}</p>
        ) : (
          <>
            <p className="text-sm text-red-400">Unavailable</p>
            {status.ollama.message && <p className="text-xs text-slate-400">{status.ollama.message}</p>}
          </>
        )}
      </div>

      {/* Index */}
      <div className="flex flex-col gap-1 border-t border-slate-800 pt-3">
        <p className="text-sm font-medium text-slate-200">Index</p>
        <p className="text-sm text-slate-300">{status.index.count} email{status.index.count === 1 ? "" : "s"} indexed</p>
      </div>
    </section>
  );
}
