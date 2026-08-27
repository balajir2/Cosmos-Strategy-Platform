import { ChatMessage } from "@/lib/api-client";

export default function ChatMessageBubble({ message }: { message: ChatMessage }) {
  if (message.message_type === "question") {
    return (
      <div className="glass-card question-card animate-slide-up">
        <div className="card-badge">Question</div>
        <h2 className="restless-question">{message.content}</h2>
      </div>
    );
  }

  if (message.message_type === "benchmark") {
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
