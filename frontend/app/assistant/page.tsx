"use client";

import { ChatIcon } from "@/components/icons";

/**
 * Placeholder — the real chat UI (useChat hook, ChatMessage/ChatInput,
 * VoiceButton, ConfirmActionCard, SSE parsing via lib/api.ts's apiStream)
 * lands in Phase 5. This page only exists so /assistant doesn't 404 from
 * the nav.
 */
export default function AssistantPage() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-slate-800 bg-slate-900/40 px-6 py-16 text-center">
      <ChatIcon className="h-8 w-8 text-slate-500" />
      <p className="text-sm text-slate-400">Assistant — coming in the next phase.</p>
    </div>
  );
}
