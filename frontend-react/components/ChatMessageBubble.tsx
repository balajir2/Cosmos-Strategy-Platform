import { ChatMessage } from "@/lib/api-client";

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

export default function ChatMessageBubble({ message }: { message: ChatMessage }) {
  if (message.message_type === "question") {
    return (
      <div className="glass-card question-card animate-slide-up">
        <div className="card-badge">Question</div>
        <h2 className="restless-question">{message.content}</h2>
      </div>
    );
  }

  if (message.message_type === "calibration_prompt") {
    return (
      <div className="glass-card question-card animate-slide-up">
        <div className="card-badge">Baseline Calibration</div>
        <h2 className="restless-question">{message.content}</h2>
      </div>
    );
  }

  if (message.message_type === "calibration_feedback") {
    return (
      <div className="glass-card recommendations-card animate-slide-up">
        <h3>
          <i className="fa-solid fa-compass"></i> Calibration Feedback
        </h3>
        <p className="recommendations-text">{message.content}</p>
      </div>
    );
  }

  if (message.message_type === "benchmark") {
    const payload = parseBenchmarkPayload(message.content);

    // No valid JSON payload - a legacy case-based session's plain-text
    // benchmark prose. Render exactly as before so those sessions are
    // visually unaffected (spec Decision 7).
    if (!payload) {
      return (
        <div className="glass-card critique-card animate-slide-up">
          <h3>
            <i className="fa-solid fa-scale-balanced"></i> Benchmark Answers
          </h3>
          <p className="critique-text" style={{ whiteSpace: "pre-wrap" }}>
            {message.content}
          </p>
        </div>
      );
    }

    return (
      <div className="evaluation-results-wrapper animate-slide-up">
        <div className="rating-card lvl-1">
          <div className="rating-icon-container"><i className="fa-solid fa-1"></i></div>
          <div className="rating-info">
            <span className="rating-label">Level 1 - Superficial</span>
            <span className="rating-title" style={{ fontSize: "0.95rem", fontWeight: 400, lineHeight: 1.5 }}>{payload.level_1}</span>
          </div>
        </div>
        <div className="rating-card lvl-2">
          <div className="rating-icon-container"><i className="fa-solid fa-2"></i></div>
          <div className="rating-info">
            <span className="rating-label">Level 2 - Needs-Based</span>
            <span className="rating-title" style={{ fontSize: "0.95rem", fontWeight: 400, lineHeight: 1.5 }}>{payload.level_2}</span>
          </div>
        </div>
        <div className="rating-card lvl-3">
          <div className="rating-icon-container"><i className="fa-solid fa-3"></i></div>
          <div className="rating-info">
            <span className="rating-label">Level 3 - Insight-Driven</span>
            <span className="rating-title" style={{ fontSize: "0.95rem", fontWeight: 400, lineHeight: 1.5 }}>{payload.level_3}</span>
          </div>
        </div>

        {payload.source_chunks.length > 0 && (
          <div className="glass-card references-card">
            <div className="references-header">
              <h3>
                <i className="fa-solid fa-book"></i> Source References
              </h3>
            </div>
            <div className="references-list">
              {payload.source_chunks.map((chunk) => (
                <div className="reference-item" key={chunk.id}>
                  <div className="ref-meta">
                    <span className="ref-source">
                      {chunk.source === "framework" ? "Framework Reference" : "Customer Document"} - {chunk.source_file}
                    </span>
                    <span className="ref-score">{Math.round(chunk.score * 100)}% match</span>
                  </div>
                  <p className="ref-text">{chunk.text}</p>
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
      <div className="glass-card recommendations-card animate-slide-up">
        <h3>
          <i className="fa-solid fa-circle-chevron-up"></i> Self-Evaluation
        </h3>
        <p className="recommendations-text">{message.content}</p>
      </div>
    );
  }

  return (
    <div
      className="glass-card animate-slide-up"
      style={{
        padding: "16px 20px",
        marginLeft: message.role === "user" ? "20%" : 0,
        marginRight: message.role === "user" ? 0 : "20%",
        background: message.role === "user" ? "rgba(0, 122, 255, 0.08)" : undefined,
      }}
    >
      <p style={{ whiteSpace: "pre-wrap" }}>{message.content}</p>
    </div>
  );
}
