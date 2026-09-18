"use client";

export interface ReadinessCheck {
  label: string;
  passed: boolean;
}

export default function ReadinessChecklist({ checks }: { checks: ReadinessCheck[] }) {
  return (
    <div className="readiness-checklist">
      {checks.map((c) => (
        <span key={c.label} className={`readiness-item ${c.passed ? "passed" : "warning"}`}>
          <i className={`fa-solid ${c.passed ? "fa-circle-check" : "fa-triangle-exclamation"}`}></i> {c.label}
        </span>
      ))}
    </div>
  );
}
