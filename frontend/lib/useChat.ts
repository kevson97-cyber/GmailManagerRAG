/**
 * useChat.ts — owns all /api/chat state for the assistant page: the
 * displayed message list (user/assistant bubbles, tool-activity chips,
 * confirm cards, errors), the in-memory API transcript, and the SSE
 * lifecycle (send, confirm/decline resume, stop, clear).
 *
 * Display vs. transcript: `messages` is what the UI renders (includes tool
 * chips and confirm cards). `transcriptRef` is what actually gets POSTed to
 * /api/chat — only user/assistant text turns, per chat.py's role whitelist
 * and engine.py's event contract (tool_call/tool_result/confirm are
 * reconstructed server-side from the confirm_token on resume, never
 * round-tripped by the client).
 */
import { useCallback, useRef, useState } from "react";
import { apiStream, ApiError } from "./api";
import type {
  ChatConfirmEvent,
  ChatDoneEvent,
  ChatErrorEvent,
  ChatMessage,
  ChatPreviewItem,
  ChatRequest,
  ChatToolCallEvent,
  ChatToolResultEvent,
  ChatTokenEvent,
} from "./types";

// ── Display message types ───────────────────────────────────────────────────

export interface DisplayUserMessage {
  id: string;
  kind: "user";
  text: string;
}

export interface DisplayAssistantMessage {
  id: string;
  kind: "assistant";
  text: string;
  streaming: boolean;
}

export type ToolChipStatus = "running" | "done";

export interface DisplayToolMessage {
  id: string;
  kind: "tool";
  name: string;
  summary?: string;
  status: ToolChipStatus;
}

export type ConfirmCardStatus = "pending" | "confirmed" | "declined";

export interface DisplayConfirmMessage {
  id: string;
  kind: "confirm";
  confirmToken: string;
  action: string;
  description: string;
  count: number;
  preview: ChatPreviewItem[];
  status: ConfirmCardStatus;
}

export interface DisplayErrorMessage {
  id: string;
  kind: "error";
  text: string;
}

export type DisplayMessage =
  | DisplayUserMessage
  | DisplayAssistantMessage
  | DisplayToolMessage
  | DisplayConfirmMessage
  | DisplayErrorMessage;

// ── Small helpers ────────────────────────────────────────────────────────────

let idCounter = 0;
function makeId(): string {
  idCounter += 1;
  return `m${idCounter}`;
}

/** Marks the most recent *running* tool chip with this name as done, or returns null if none exists. */
function resolveLatestRunningTool(
  prev: DisplayMessage[],
  name: string,
  summary?: string
): DisplayMessage[] | null {
  for (let i = prev.length - 1; i >= 0; i--) {
    const m = prev[i];
    if (m.kind === "tool" && m.name === name && m.status === "running") {
      const next = prev.slice();
      next[i] = { ...m, status: "done", summary: summary ?? m.summary };
      return next;
    }
  }
  return null;
}

function friendlyStreamError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return "Unauthorized — check your API token in Settings.";
    return err.detail || "Request to the assistant failed.";
  }
  return "Connection to the assistant was lost.";
}

export interface UseChatResult {
  messages: DisplayMessage[];
  isStreaming: boolean;
  pendingConfirm: DisplayConfirmMessage | null;
  /** confirm_token of the card currently being resolved (resume stream in flight), if any. */
  resolvingToken: string | null;
  send: (text: string) => void;
  respondToConfirm: (confirmed: boolean) => void;
  stop: () => void;
  clear: () => void;
}

export function useChat(): UseChatResult {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<DisplayConfirmMessage | null>(null);
  const [resolvingToken, setResolvingToken] = useState<string | null>(null);

  // Refs mirror the state above so the async SSE callbacks (which close over
  // whatever render they started in) always see the latest value instead of
  // a stale one from the render that kicked off the stream.
  const transcriptRef = useRef<ChatMessage[]>([]);
  const isStreamingRef = useRef(false);
  const pendingConfirmRef = useRef<DisplayConfirmMessage | null>(null);
  const respondingRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  // Bumped by clear() so a stream's catch/finally that resolves *after* the
  // conversation has already been wiped can no-op instead of resurrecting
  // stale state (e.g. re-appending a partial assistant reply to a transcript
  // that was just cleared, or clobbering a newer stream's AbortController).
  const sessionRef = useRef(0);

  const setStreamingBoth = useCallback((v: boolean) => {
    isStreamingRef.current = v;
    setIsStreaming(v);
  }, []);

  const setPendingConfirmBoth = useCallback((v: DisplayConfirmMessage | null) => {
    pendingConfirmRef.current = v;
    setPendingConfirm(v);
  }, []);

  /** Runs one agent turn as SSE and applies every event to `messages`/`transcriptRef`. Shared by send() and respondToConfirm(). */
  const runStream = useCallback(
    async (body: ChatRequest) => {
      const session = sessionRef.current;
      setStreamingBoth(true);
      const controller = new AbortController();
      abortControllerRef.current = controller;

      let assistantId: string | null = null;
      let assistantText = "";
      let sawAwaitingConfirmation = false;

      const ensureAssistantBubble = () => {
        if (assistantId !== null) return;
        assistantId = makeId();
        const id = assistantId;
        setMessages((prev) => [...prev, { id, kind: "assistant", text: "", streaming: true }]);
      };

      const finalizeAssistant = () => {
        if (assistantId === null) return;
        const id = assistantId;
        setMessages((prev) =>
          prev.map((m) => (m.id === id && m.kind === "assistant" ? { ...m, streaming: false } : m))
        );
        if (assistantText.trim()) {
          transcriptRef.current = [...transcriptRef.current, { role: "assistant", content: assistantText }];
        }
        assistantId = null;
      };

      try {
        await apiStream(
          "/api/chat",
          { method: "POST", body: JSON.stringify(body) },
          (name, data) => {
            switch (name) {
              case "token": {
                const { text } = data as ChatTokenEvent;
                ensureAssistantBubble();
                assistantText += text;
                const id = assistantId;
                setMessages((prev) =>
                  prev.map((m) => (m.id === id && m.kind === "assistant" ? { ...m, text: m.text + text } : m))
                );
                break;
              }
              case "tool_call": {
                const { name: toolName } = data as ChatToolCallEvent;
                setMessages((prev) => [...prev, { id: makeId(), kind: "tool", name: toolName, status: "running" }]);
                break;
              }
              case "tool_result": {
                const { name: toolName, summary } = data as ChatToolResultEvent;
                setMessages((prev) => resolveLatestRunningTool(prev, toolName, summary) ?? [
                  ...prev,
                  { id: makeId(), kind: "tool", name: toolName, summary, status: "done" },
                ]);
                break;
              }
              case "confirm": {
                const c = data as ChatConfirmEvent;
                const confirmMsg: DisplayConfirmMessage = {
                  id: makeId(),
                  kind: "confirm",
                  confirmToken: c.confirm_token,
                  action: c.action,
                  description: c.description,
                  count: c.count,
                  preview: c.preview ?? [],
                  status: "pending",
                };
                setMessages((prev) => {
                  const resolved = resolveLatestRunningTool(prev, c.action) ?? prev;
                  return [...resolved, confirmMsg];
                });
                setPendingConfirmBoth(confirmMsg);
                // The engine always pauses the turn right after emitting
                // confirm; set this here (not just on done) so a dropped
                // connection between the two events can't clear the pending
                // card and leave it with dead buttons.
                sawAwaitingConfirmation = true;
                break;
              }
              case "done": {
                const { finish_reason } = data as ChatDoneEvent;
                finalizeAssistant();
                if (finish_reason === "awaiting_confirmation") sawAwaitingConfirmation = true;
                break;
              }
              case "error": {
                const { message } = data as ChatErrorEvent;
                finalizeAssistant();
                setMessages((prev) => [...prev, { id: makeId(), kind: "error", text: message }]);
                break;
              }
              default:
                break;
            }
          },
          controller.signal
        );
      } catch (err) {
        if (!controller.signal.aborted && sessionRef.current === session) {
          finalizeAssistant();
          setMessages((prev) => [...prev, { id: makeId(), kind: "error", text: friendlyStreamError(err) }]);
        }
      } finally {
        // A clear() (or a stream that started a new session for some other
        // reason) already reset everything this stream would otherwise touch
        // — leave it alone rather than resurrecting stale state.
        if (sessionRef.current === session) {
          finalizeAssistant();
          setStreamingBoth(false);
          abortControllerRef.current = null;
          if (!sawAwaitingConfirmation) setPendingConfirmBoth(null);
        }
      }
    },
    [setPendingConfirmBoth, setStreamingBoth]
  );

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreamingRef.current || pendingConfirmRef.current) return;
      setMessages((prev) => [...prev, { id: makeId(), kind: "user", text: trimmed }]);
      transcriptRef.current = [...transcriptRef.current, { role: "user", content: trimmed }];
      void runStream({ messages: transcriptRef.current });
    },
    [runStream]
  );

  const respondToConfirm = useCallback(
    (confirmed: boolean) => {
      if (respondingRef.current) return;
      const current = pendingConfirmRef.current;
      if (!current) return;
      respondingRef.current = true;
      const token = current.confirmToken;

      setPendingConfirmBoth(null);
      setResolvingToken(token);
      setMessages((prev) =>
        prev.map((m) =>
          m.kind === "confirm" && m.confirmToken === token
            ? { ...m, status: confirmed ? "confirmed" : "declined" }
            : m
        )
      );

      void runStream({
        messages: transcriptRef.current,
        confirm_token: token,
        cancelled: !confirmed,
      }).finally(() => {
        setResolvingToken((t) => (t === token ? null : t));
        respondingRef.current = false;
      });
    },
    [runStream, setPendingConfirmBoth]
  );

  const stop = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  const clear = useCallback(() => {
    sessionRef.current += 1;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    transcriptRef.current = [];
    respondingRef.current = false;
    setMessages([]);
    setResolvingToken(null);
    setPendingConfirmBoth(null);
    setStreamingBoth(false);
  }, [setPendingConfirmBoth, setStreamingBoth]);

  return { messages, isStreaming, pendingConfirm, resolvingToken, send, respondToConfirm, stop, clear };
}
