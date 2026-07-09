"use client";

import { useEffect, useRef, useState } from "react";
import VoiceButton from "./VoiceButton";

interface Props {
  onSend: (text: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  /** True while a confirm card is unresolved — blocks new turns until the user responds. */
  disabled: boolean;
}

// ~5 lines at text-sm line-height plus vertical padding.
const MAX_TEXTAREA_HEIGHT = 132;

function StopIcon() {
  return <span className="h-3 w-3 rounded-sm bg-white" aria-hidden="true" />;
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5 -translate-x-px" aria-hidden="true">
      <path d="M3.4 20.6 21 12 3.4 3.4 3 10l12 2-12 2z" />
    </svg>
  );
}

export default function ChatInput({ onSend, onStop, isStreaming, disabled }: Props) {
  const [value, setValue] = useState("");
  const [touchPrimary, setTouchPrimary] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reads a media query against the device, an external signal
    setTouchPrimary(typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)")?.matches === true);
  }, []);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [value]);

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Touch devices: Enter always inserts a newline; sending is button-only.
    if (e.key !== "Enter" || e.shiftKey || touchPrimary) return;
    e.preventDefault();
    handleSend();
  }

  return (
    <div className="border-t border-slate-800 bg-slate-950/95 px-3 py-2.5 backdrop-blur">
      {disabled && <p className="mb-1.5 text-xs text-amber-400">Respond to the confirmation above to continue.</p>}
      <div className="flex items-end gap-2">
        <VoiceButton disabled={disabled || isStreaming} onTranscript={setValue} />

        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={disabled ? "Waiting for confirmation…" : "Ask about your inbox…"}
          className="min-h-11 flex-1 resize-none rounded-2xl border border-slate-700 bg-slate-900 px-3.5 py-2.5 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-indigo-500 disabled:opacity-50"
          style={{ maxHeight: MAX_TEXTAREA_HEIGHT }}
        />

        {isStreaming ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-slate-700 text-white hover:bg-slate-600"
          >
            <StopIcon />
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSend}
            disabled={disabled || !value.trim()}
            aria-label="Send message"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-indigo-500 text-white hover:bg-indigo-400 disabled:opacity-40"
          >
            <SendIcon />
          </button>
        )}
      </div>
    </div>
  );
}
