import { ChatMessage } from "@/lib/api-client";
import styles from "@/app/client/case/[caseId]/chat/chat.module.css";

interface BenchmarkSourceChunk {
  id: number;
  source: "framework" | "customer_document";
  source_file: string;
  phase?: string;
  slide_number?: number;
  text: string;
  score: number;
}

interface BenchmarkPayload {
  level_1: string;
  level_2: string;
  level_3: string;
  source_chunks: BenchmarkSourceChunk[];
}

function parseBenchmarkPayload(content: string): BenchmarkPayload | null {
  try {
    const parsed = JSON.parse(content);
    if (parsed && typeof parsed.level_1 === "string" && typeof parsed.level_2 === "string" && typeof parsed.level_3 === "string") {
      return { ...parsed, source_chunks: Array.isArray(parsed.source_chunks) ? parsed.source_chunks : [] };
    }
    return null;
  } catch {
    return null;
  }
}

export type SelfEvalLevel = 1 | 2 | 3;

interface ChatMessageBubbleProps {
  message: ChatMessage;
  interactive?: boolean;
  selectedLevel?: SelfEvalLevel | null;
  onSelectLevel?: (level: SelfEvalLevel) => void;
}

export default function ChatMessageBubble({ message, interactive, selectedLevel, onSelectLevel }: ChatMessageBubbleProps) {
  if (message.message_type === "question") {
    return (
      <div className={styles.card}>
        <div className={styles.cardBadge}>Question</div>
        <h2 className={styles.questionText}>{message.content}</h2>
      </div>
    );
  }

  if (message.message_type === "calibration_prompt") {
    return (
      <div className={styles.card}>
        <div className={styles.cardBadge}>Baseline Calibration</div>
        <h2 className={styles.questionText}>{message.content}</h2>
      </div>
    );
  }

  if (message.message_type === "calibration_feedback") {
    return (
      <div className={styles.card}>
        <h3>
          <i className="fa-solid fa-compass"></i> Calibration Feedback
        </h3>
        <p className={styles.calibrationFeedback}>{message.content}</p>
      </div>
    );
  }

  if (message.message_type === "benchmark") {
    const payload = parseBenchmarkPayload(message.content);

    // No valid JSON payload - a legacy case-based session's plain-text
    // benchmark prose. Render exactly as before, just restyled.
    if (!payload) {
      return (
        <div className={styles.card}>
          <h3>
            <i className="fa-solid fa-scale-balanced"></i> Benchmark Answers
          </h3>
          <p style={{ whiteSpace: "pre-wrap" }}>{message.content}</p>
        </div>
      );
    }

    const levels: Array<{ n: SelfEvalLevel; label: string; text: string; tagClass: string }> = [
      { n: 1, label: "Level 1 - Superficial", text: payload.level_1, tagClass: styles.levelTag1 },
      { n: 2, label: "Level 2 - Needs-Based", text: payload.level_2, tagClass: styles.levelTag2 },
      { n: 3, label: "Level 3 - Insight-Driven", text: payload.level_3, tagClass: styles.levelTag3 },
    ];

    return (
      <div className={styles.benchmarkWrap}>
        <div className={styles.benchLabel}>
          {interactive ? "How this compares — click the level closest to your answer" : "How this compares"}
        </div>
        <div className={styles.benchGrid}>
          {levels.map(({ n, label, text, tagClass }) => {
            const isSelected = Boolean(interactive) && selectedLevel === n;
            const classes = [
              styles.levelCard,
              interactive ? styles.levelCardInteractive : "",
              isSelected ? styles.levelCardSelected : "",
            ].join(" ");
            const Tag = interactive ? "button" : "div";
            return (
              <Tag
                key={n}
                type={interactive ? "button" : undefined}
                className={classes}
                onClick={interactive && onSelectLevel ? () => onSelectLevel(n) : undefined}
              >
                <span className={`${styles.levelTag} ${tagClass}`}>{label}</span>
                <span className={styles.levelText}>{text}</span>
                {isSelected && <span className={styles.selectedChip}>&#10003; You&apos;re here</span>}
              </Tag>
            );
          })}
        </div>

        {payload.source_chunks.length > 0 && (
          <div className={styles.referencesCard}>
            <h3>
              <i className="fa-solid fa-book"></i> Source References
            </h3>
            <div>
              {payload.source_chunks.map((chunk) => (
                <div className={styles.referenceItem} key={chunk.id}>
                  <div className={styles.refMeta}>
                    <span className={styles.refSource}>
                      {chunk.source === "framework" ? "Framework Reference" : "Customer Document"} - {chunk.source_file}
                    </span>
                    <span className={styles.refScore}>{Math.round(chunk.score * 100)}% match</span>
                  </div>
                  <p>{chunk.text}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (message.message_type === "self_rating_prompt") {
    return (
      <div className={styles.card}>
        <h3>
          <i className="fa-solid fa-circle-chevron-up"></i> Self-Evaluation
        </h3>
        <p className={styles.calibrationFeedback}>{message.content}</p>
      </div>
    );
  }

  return (
    <div className={message.role === "user" ? styles.userBubble : styles.genericBubble}>
      <p style={{ whiteSpace: "pre-wrap" }}>{message.content}</p>
    </div>
  );
}
