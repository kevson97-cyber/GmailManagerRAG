"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ChatInput from "@/components/ChatInput";
import ChatMessage from "@/components/ChatMessage";
import ConfirmActionCard from "@/components/ConfirmActionCard";
import { ChatIcon } from "@/components/icons";
import { apiFetch } from "@/lib/api";
import type { StatusResponse } from "@/lib/types";
import { useChat } from "@/lib/useChat";

const SUGGESTIONS = [
  "What subscriptions email me most?",
  "Summarize emails from my top sender",
  "How many promotions am I sitting on?",
  "Trash emails from a sender…",
];

// Bounded independently of AppShell's own layout so the message list always
// gets a definite, scrollable height regardless of viewport size.
const LIST_STYLE = { maxHeight: "min(65vh, calc(100dvh - 300px))", minHeight: "220px" };

// How close to the bottom (px) counts as "still following the conversation" —
// past this, new content no longer auto-scrolls the view.
const AUTO_SCROLL_THRESHOLD = 64;

export default function AssistantPage() {
  const chat = useChat();
  const [ollamaAvailable, setOllamaAvailable] = useState<boolean | null>(null);

  const listRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const prevMessageCount = useRef(0);

  const checkOllama = useCallback(async () => {
    try {
      const status = await apiFetch<StatusResponse>("/api/status");
      setOllamaAvailable(status.ollama.available);
    } catch {
      // Backend unreachable/unauthorized — leave the banner alone; that's a
      // bigger problem than Ollama and is already surfaced on the Sync page.
    }
  }, []);

  useEffect(() => {
    // Fetch on mount — synchronizing with the backend, an external system.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void checkOllama();
  }, [checkOllama]);

  // Re-check Ollama status whenever a new error bubble shows up (a send that failed).
  useEffect(() => {
    if (chat.messages.length > prevMessageCount.current) {
      const added = chat.messages.slice(prevMessageCount.current);
      if (added.some((m) => m.kind === "error")) void checkOllama();
    }
    prevMessageCount.current = chat.messages.length;
  }, [chat.messages, checkOllama]);

  // Track whether the user has scrolled away from the bottom of the message list.
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    function onScroll() {
      if (!el) return;
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      setAutoScroll(distanceFromBottom < AUTO_SCROLL_THRESHOLD);
    }
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // Auto-scroll to bottom on new content, unless the user scrolled up to read history.
  useEffect(() => {
    if (!autoScroll) return;
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [chat.messages, autoScroll]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-100">Assistant</h1>
        <button
          type="button"
          onClick={chat.clear}
          disabled={chat.messages.length === 0}
          className="min-h-11 rounded-lg border border-slate-700 px-3 text-sm font-medium text-slate-200 hover:bg-slate-800 disabled:opacity-40"
        >
          New chat
        </button>
      </div>

      {ollamaAvailable === false && (
        <div className="rounded-xl border border-amber-900/50 bg-amber-950/30 px-4 py-2.5 text-sm text-amber-300">
          Ollama is offline. Run <code className="rounded bg-black/30 px-1 py-0.5 font-mono text-xs">ollama serve</code>{" "}
          on the backend PC (and <code className="rounded bg-black/30 px-1 py-0.5 font-mono text-xs">ollama pull qwen3:4b</code>{" "}
          if the model isn&apos;t pulled yet), then try again.
        </div>
      )}

      <div
        ref={listRef}
        style={LIST_STYLE}
        className="flex flex-col gap-3 overflow-y-auto overscroll-contain rounded-xl border border-slate-800 bg-slate-900/20 p-3"
      >
        {chat.messages.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 px-4 py-8 text-center">
            <ChatIcon className="h-8 w-8 text-slate-600" />
            <p className="text-sm text-slate-400">
              Ask about your inbox, or tell it to clean something up — destructive actions always ask first.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => chat.send(s)}
                  className="min-h-11 rounded-full border border-slate-700 px-3.5 text-sm text-slate-300 hover:bg-slate-800"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          chat.messages.map((m) =>
            m.kind === "confirm" ? (
              <ConfirmActionCard
                key={m.id}
                message={m}
                resolving={chat.resolvingToken === m.confirmToken}
                onConfirm={() => chat.respondToConfirm(true)}
                onDecline={() => chat.respondToConfirm(false)}
              />
            ) : (
              <ChatMessage key={m.id} message={m} />
            )
          )
        )}
      </div>

      <ChatInput
        onSend={chat.send}
        onStop={chat.stop}
        isStreaming={chat.isStreaming}
        disabled={chat.pendingConfirm !== null}
      />
    </div>
  );
}
