"use client";

import { useEffect, useState } from "react";
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
 *
 * `visible` starts false so server-rendered output and the client's
 * first hydration render match exactly (window/localStorage aren't
 * available during SSR) — the real eligibility/dismissal state is
 * computed post-mount in the effect below.
 */
export default function IosDictationHint() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!isIosWebKit()) return;
    try {
      if (localStorage.getItem(DISMISS_KEY) === "1") return;
    } catch {
      // Storage read failed (private mode, etc.) - fall through and
      // treat as "not dismissed" rather than hiding the tip forever.
    }
    setVisible(true);
  }, []);

  if (!visible) return null;

  const handleDismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // ignore (private mode etc.)
    }
    setVisible(false);
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
