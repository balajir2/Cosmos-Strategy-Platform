import { useCallback, useEffect, useRef, useState } from "react";

interface SpeechRecognitionResultLite {
  readonly isFinal: boolean;
  readonly 0: { readonly transcript: string };
}

interface SpeechRecognitionResultListLite {
  readonly length: number;
  [index: number]: SpeechRecognitionResultLite;
}

interface SpeechRecognitionEventLite extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultListLite;
}

interface SpeechRecognitionErrorEventLite extends Event {
  readonly error: string;
  readonly message?: string;
}

interface SpeechRecognitionLite extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onstart: ((this: SpeechRecognitionLite, ev: Event) => unknown) | null;
  onend: ((this: SpeechRecognitionLite, ev: Event) => unknown) | null;
  onresult:
    | ((this: SpeechRecognitionLite, ev: SpeechRecognitionEventLite) => unknown)
    | null;
  onerror:
    | ((
        this: SpeechRecognitionLite,
        ev: SpeechRecognitionErrorEventLite,
      ) => unknown)
    | null;
}

interface SpeechRecognitionConstructorLite {
  new (): SpeechRecognitionLite;
}

declare global {
  interface Window {
    webkitSpeechRecognition?: SpeechRecognitionConstructorLite;
    SpeechRecognition?: SpeechRecognitionConstructorLite;
  }
}

const SAFETY_TIMEOUT_MS = 120_000;
const RECOGNITION_LANG = "en-IN";

export interface UseSpeechRecognition {
  isSupported: boolean;
  isListening: boolean;
  transcript: string;
  error: string | null;
  start: () => void;
  stop: () => void;
  reset: () => void;
}

function getCtor(): SpeechRecognitionConstructorLite | null {
  if (typeof window === "undefined") return null;
  return window.webkitSpeechRecognition ?? window.SpeechRecognition ?? null;
}

export function useSpeechRecognition(): UseSpeechRecognition {
  const Ctor = getCtor();
  const isSupported = Ctor !== null;

  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionLite | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finalTranscriptRef = useRef("");

  const clearSafety = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    clearSafety();
    const r = recognitionRef.current;
    if (r) {
      try {
        r.stop();
      } catch {
        // ignore - already stopped
      }
    }
  }, [clearSafety]);

  const start = useCallback(() => {
    if (!Ctor) return;
    if (recognitionRef.current) return; // idempotent: already listening

    setError(null);
    finalTranscriptRef.current = "";
    setTranscript("");

    const r = new Ctor();
    r.lang = RECOGNITION_LANG;
    r.continuous = false;
    r.interimResults = true;
    r.maxAlternatives = 1;

    r.onstart = () => setIsListening(true);
    r.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
      clearSafety();
    };
    r.onresult = (ev: SpeechRecognitionEventLite) => {
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        if (ev.results[i].isFinal) {
          finalTranscriptRef.current += ev.results[i][0].transcript;
        }
      }
      setTranscript(finalTranscriptRef.current);
    };
    r.onerror = (ev: SpeechRecognitionErrorEventLite) => {
      if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
        setError("Microphone blocked — check browser settings to enable voice.");
      } else if (ev.error === "no-speech") {
        // Silent - common, not actionable
      } else {
        setError(`Voice error: ${ev.error}`);
      }
    };

    recognitionRef.current = r;
    r.start();

    timeoutRef.current = setTimeout(() => {
      stop();
    }, SAFETY_TIMEOUT_MS);
  }, [Ctor, clearSafety, stop]);

  const reset = useCallback(() => {
    finalTranscriptRef.current = "";
    setTranscript("");
    setError(null);
  }, []);

  // Unmount cleanup
  useEffect(() => {
    return () => {
      clearSafety();
      const r = recognitionRef.current;
      if (r) {
        try {
          r.abort();
        } catch {
          // ignore
        }
      }
    };
  }, [clearSafety]);

  return { isSupported, isListening, transcript, error, start, stop, reset };
}
