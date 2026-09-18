"use client";

export default function ConfirmDialog({
  message,
  confirmLabel = "Confirm",
  danger,
  onConfirm,
  onCancel,
}: {
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60 }}
      onClick={onCancel}
    >
      <div className="glass-card question-card animate-slide-up" style={{ maxWidth: 420, width: "90%" }} onClick={(e) => e.stopPropagation()}>
        <p style={{ whiteSpace: "pre-wrap" }}>{message}</p>
        <div className="actions-row">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
          <button
            type="button"
            className="btn btn-primary"
            style={danger ? { background: "var(--error)" } : undefined}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
