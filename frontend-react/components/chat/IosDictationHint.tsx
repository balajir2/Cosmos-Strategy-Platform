"use client";

import { useState } from "react";
import styles from "@/app/client/case/[caseId]/chat/chat.module.css";

const DISMISS_KEY = "cosmos_ios_dictation_hint_dismissed";

function isIosWebKit(): boolean {
  if (typeof window === "undefined") return false;
  if ("webkitSpeechRecognition" in window) return false;
  if ("SpeechRecognition" in window) return false;
  return /iPad|iPhone|iPod/.test(navigator.userAgent);
}

/**
 * Inline tip for iOS users — Apple WebKit doesn't expose
 * SpeechRecognition, so we point them at the native keyboard
 * dictation. Dismissible; dismissal persists in localStorage.
 */
export default function IosDictationHint() {
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === "undefined") return true;
    try {
      return localStorage.getItem(DISMISS_KEY) === "1";
    } catch {
      return false;
    }
  });

  if (dismissed) return null;
  if (!isIosWebKit()) return null;

  const handleDismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // ignore (private mode etc.)
    }
    setDismissed(true);
  };

  return (
    <div className={styles.iosHint}>
      <p>
        <strong>iPhone?</strong> Tap the microphone on your keyboard to speak instead of typing.
      </p>
      <button type="button" onClick={handleDismiss} aria-label="Dismiss tip" className={styles.iosHintDismiss}>
        &times;
      </button>
    </div>
  );
}
