"use client";

import { useEffect } from "react";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import styles from "@/app/client/case/[caseId]/chat/chat.module.css";

interface MicButtonProps {
  onTranscript: (text: string) => void;
  disabled?: boolean;
}

export default function MicButton({ onTranscript, disabled }: MicButtonProps) {
  const { isSupported, isListening, transcript, error, start, stop, reset } = useSpeechRecognition();

  // When recognition ends and we have a transcript, commit it. We track
  // `isListening` flipping false as the signal; the final transcript is
  // already buffered at that point.
  useEffect(() => {
    if (!isListening && transcript.trim()) {
      onTranscript(transcript.trim());
      reset();
    }
  }, [isListening, transcript, onTranscript, reset]);

  if (!isSupported) return null;

  const beginListen = () => {
    if (disabled) return;
    start();
  };
  const endListen = () => {
    stop();
  };

  return (
    <>
      <button
        type="button"
        aria-label={isListening ? "Listening — release to stop" : "Hold to speak your answer"}
        disabled={disabled}
        onMouseDown={beginListen}
        onMouseUp={endListen}
        onMouseLeave={endListen}
        onTouchStart={(e) => {
          e.preventDefault();
          beginListen();
        }}
        onTouchEnd={(e) => {
          e.preventDefault();
          endListen();
        }}
        onTouchCancel={endListen}
        className={`${styles.micBtn} ${isListening ? styles.micBtnListening : ""}`}
      >
        <i className="fa-solid fa-microphone"></i>
      </button>
      {isListening && <span className={styles.micStatus}>Listening…</span>}
      {error && !isListening && <span className={styles.errorText}>{error}</span>}
    </>
  );
}
