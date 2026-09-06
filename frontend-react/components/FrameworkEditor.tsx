"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getFramework, createFrameworkStage, updateFrameworkStage, deleteFrameworkStage,
  createFrameworkQuestion, updateFrameworkQuestion, deleteFrameworkQuestion, generateFramework,
  ProcessDetail,
} from "@/lib/api-client";

export default function FrameworkEditor({ projectId }: { projectId: number }) {
  const [framework, setFramework] = useState<ProcessDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newStageName, setNewStageName] = useState("");
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);

  const reload = useCallback(() => {
    getFramework(projectId).then(setFramework).catch(() => setError("Could not load the framework."));
  }, [projectId]);

  useEffect(() => { reload(); }, [reload]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the framework.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddStage() {
    const name = newStageName.trim();
    if (!name) return;
    setNewStageName("");
    await run(() => createFrameworkStage(projectId, name));
  }

  async function handleAddQuestion(stageId: number) {
    const level = window.prompt("Level (e.g. Level 3: Brand Positioning)");
    if (!level) return;
    const text = window.prompt("Question text");
    if (!text) return;
    const ownerRole = window.prompt("Owner role (e.g. Brand Manager, CMO, CEO)");
    if (!ownerRole) return;
    const searchQuery = window.prompt("Search query (optional)") || undefined;
    const reviewerRole = window.prompt("Reviewer role (optional)") || undefined;
    await run(() => createFrameworkQuestion(projectId, stageId, { level, text, owner_role: ownerRole, search_query: searchQuery, reviewer_role: reviewerRole }));
  }

  async function handleGenerate() {
    if (!window.confirm("This replaces every stage and question in this project's framework with an AI-drafted set from Cosmos Knowledge. Continue?")) return;
    setGenerating(true);
    setError(null);
    try {
      await generateFramework(projectId);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate the framework.");
    } finally {
      setGenerating(false);
    }
  }

  if (!framework) {
    return <div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading framework...</div>;
  }

  return (
    <div className="glass-card framework-card">
      <h3><i className="fa-solid fa-sitemap"></i> Framework</h3>
      <p className="dropzone-hint">This engagement&apos;s questions. Edit stages and questions below; clients see your latest version.</p>

      <div className="answer-wrapper">
        <label htmlFor="new-stage-input">Add stage</label>
        <div className="assign-row">
          <input id="new-stage-input" type="text" value={newStageName} onChange={(e) => setNewStageName(e.target.value)} placeholder="e.g. Aim & SWOT" />
          <button className="btn btn-secondary" onClick={handleAddStage} disabled={busy || generating}><i className="fa-solid fa-plus"></i> Add</button>
        </div>
      </div>

      <button className="btn btn-secondary" onClick={handleGenerate} disabled={busy || generating}>
        <i className="fa-solid fa-wand-magic-sparkles"></i> {generating ? "Generating..." : "Generate Framework from Cosmos Knowledge"}
      </button>

      {framework.stages.map((stage) => (
        <div className="framework-stage" key={stage.id}>
          <div className="framework-stage-header">
            <span className="framework-stage-name">{stage.name}</span>
            <span className="framework-stage-actions">
              <button className="btn btn-secondary" title="Move up" disabled={busy || generating} onClick={() => run(() => updateFrameworkStage(projectId, stage.id, { action: "move_up" }))}><i className="fa-solid fa-arrow-up"></i></button>
              <button className="btn btn-secondary" title="Move down" disabled={busy || generating} onClick={() => run(() => updateFrameworkStage(projectId, stage.id, { action: "move_down" }))}><i className="fa-solid fa-arrow-down"></i></button>
              <button className="btn btn-secondary" title="Rename" disabled={busy || generating} onClick={() => { const n = window.prompt("Stage name", stage.name); if (n) run(() => updateFrameworkStage(projectId, stage.id, { name: n })); }}><i className="fa-solid fa-pen"></i></button>
              <button className="btn btn-secondary" title="Delete stage" disabled={busy || generating} onClick={() => { if (window.confirm(`Delete stage "${stage.name}" and all its questions?`)) run(() => deleteFrameworkStage(projectId, stage.id)); }}><i className="fa-solid fa-trash"></i></button>
            </span>
          </div>

          {stage.questions.map((q) => {
            const guidance = q.guidance?.[0]?.content ?? "";
            return (
              <div className="framework-question" key={q.id}>
                <div className="framework-question-level">
                  {q.level}
                  {q.ai_generated && <span className="role-tag" style={{ marginLeft: 8 }}>AI-drafted</span>}
                </div>
                <div className="framework-question-text">{q.text}</div>
                <div className="framework-question-meta">
                  <span className="dropzone-hint">Owner: {q.owner_role}{q.reviewer_role ? ` · Reviewer: ${q.reviewer_role}` : ""}</span>
                </div>
                <div className="framework-question-actions">
                  <button className="btn btn-secondary" disabled={busy || generating} onClick={() => run(() => updateFrameworkQuestion(projectId, q.id, { action: "move_up" }))}><i className="fa-solid fa-arrow-up"></i></button>
                  <button className="btn btn-secondary" disabled={busy || generating} onClick={() => run(() => updateFrameworkQuestion(projectId, q.id, { action: "move_down" }))}><i className="fa-solid fa-arrow-down"></i></button>
                  <button className="btn btn-secondary" disabled={busy || generating} onClick={() => {
                    const text = window.prompt("Question text", q.text); if (!text) return;
                    const level = window.prompt("Level", q.level) || q.level;
                    const owner = window.prompt("Owner role", q.owner_role) || q.owner_role;
                    const searchQuery = window.prompt("Search query", q.search_query ?? "") || undefined;
                    const reviewer = window.prompt("Reviewer role", q.reviewer_role ?? "") || undefined;
                    const g = window.prompt("Guidance (framework text)", guidance);
                    run(() => updateFrameworkQuestion(projectId, q.id, { text, level, owner_role: owner, search_query: searchQuery, reviewer_role: reviewer, guidance: g === null ? undefined : g }));
                  }}><i className="fa-solid fa-pen"></i></button>
                  <button className="btn btn-secondary" disabled={busy || generating} onClick={() => { if (window.confirm("Delete this question?")) run(() => deleteFrameworkQuestion(projectId, q.id)); }}><i className="fa-solid fa-trash"></i></button>
                </div>
                {guidance && <div className="framework-guidance"><i className="fa-solid fa-book"></i> {guidance}</div>}
              </div>
            );
          })}

          <button className="btn btn-secondary" disabled={busy || generating} onClick={() => handleAddQuestion(stage.id)}><i className="fa-solid fa-plus"></i> Add question</button>
        </div>
      ))}

      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
