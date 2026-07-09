"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SpeechRecognition, SpeechRecognitionConstructor } from "@/lib/speech";

interface Props {
  /** Disable while streaming or while a confirmation is unresolved. */
  disabled?: boolean;
  /** Called with the running transcript (interim results overwrite each other; the final result is the last call). */
  onTranscript: (text: string) => void;
}

function getRecognitionCtor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

/**
 * Tap-to-dictate button built on the (still non-standard) Web Speech API.
 * Renders nothing if the browser lacks SpeechRecognition or the page isn't a
 * secure context — both getUserMedia and SpeechRecognition require https (or
 * localhost), and Firefox ships neither prefix at all.
 */
export default function VoiceButton({ disabled = false, onTranscript }: Props) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  useEffect(() => {
    const secure = typeof window !== "undefined" && window.isSecureContext;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- feature detection against the browser, an external system
    setSupported(Boolean(secure && getRecognitionCtor()));
  }, []);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
  }, []);

  // Stop recognition the moment the caller disables us (e.g. a stream starts).
  useEffect(() => {
    if (disabled) stopListening();
  }, [disabled, stopListening]);

  // Stop recognition on unmount.
  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!permissionDenied) return;
    const id = window.setTimeout(() => setPermissionDenied(false), 4000);
    return () => window.clearTimeout(id);
  }, [permissionDenied]);

  function handleClick() {
    if (disabled) return;

    if (listening) {
      recognitionRef.current?.stop();
      return;
    }

    const Ctor = getRecognitionCtor();
    if (!Ctor) return;

    setPermissionDenied(false);
    const recognition = new Ctor();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.onresult = (event) => {
      let text = "";
      for (let i = 0; i < event.results.length; i++) {
        text += event.results[i]?.[0]?.transcript ?? "";
      }
      onTranscript(text);
      if (event.results[event.results.length - 1]?.isFinal) {
        recognition.stop();
      }
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        setPermissionDenied(true);
      }
      // "no-speech" and other transient errors: onend fires next and resets silently.
    };

    recognition.onend = () => {
      setListening(false);
      recognitionRef.current = null;
    };

    recognitionRef.current = recognition;
    setListening(true);
    recognition.start();
  }

  if (!supported) return null;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled}
        aria-label={listening ? "Stop voice input" : "Start voice input"}
        aria-pressed={listening}
        className={`relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full border transition-colors disabled:opacity-40 ${
          listening
            ? "border-red-500 bg-red-500/20 text-red-400"
            : "border-slate-700 text-slate-300 hover:bg-slate-800"
        }`}
      >
        {listening && (
          <span className="absolute inset-0 -z-10 animate-ping rounded-full bg-red-500/30" aria-hidden="true" />
        )}
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.75}
          className="h-5 w-5"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 18.75a6 6 0 0 0 6-6v-1.5m-12 0v1.5a6 6 0 0 0 6 6Zm0 0v3.75m-3.75 0h7.5M12 15.75a3 3 0 0 1-3-3V4.5a3 3 0 1 1 6 0v8.25a3 3 0 0 1-3 3Z"
          />
        </svg>
      </button>
      {permissionDenied && (
        <p
          role="alert"
          className="absolute bottom-full left-1/2 mb-1.5 w-max max-w-[200px] -translate-x-1/2 rounded-lg border border-red-900/50 bg-red-950 px-2.5 py-1.5 text-xs text-red-300 shadow-lg"
        >
          Microphone permission denied
        </p>
      )}
    </div>
  );
}
