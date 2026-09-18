"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getFramework, createFrameworkStage, updateFrameworkStage, deleteFrameworkStage,
  createFrameworkQuestion, updateFrameworkQuestion, deleteFrameworkQuestion, generateFramework,
  ProcessDetail, Question,
} from "@/lib/api-client";
import ConfirmDialog from "./ConfirmDialog";

type QuestionForm = {
  level: string;
  text: string;
  ownerRole: string;
  searchQuery: string;
  reviewerRole: string;
  guidance: string;
};

const EMPTY_QUESTION_FORM: QuestionForm = { level: "", text: "", ownerRole: "", searchQuery: "", reviewerRole: "", guidance: "" };

function questionToForm(q: Question): QuestionForm {
  return {
    level: q.level,
    text: q.text,
    ownerRole: q.owner_role,
    searchQuery: q.search_query ?? "",
    reviewerRole: q.reviewer_role ?? "",
    guidance: q.guidance?.[0]?.content ?? "",
  };
}

type PendingConfirm = { message: string; confirmLabel?: string; danger?: boolean; onConfirm: () => void };

export default function FrameworkEditor({ projectId, onChange }: { projectId: number; onChange?: () => void }) {
  const [framework, setFramework] = useState<ProcessDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newStageName, setNewStageName] = useState("");
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [confirmState, setConfirmState] = useState<PendingConfirm | null>(null);

  const [editingStageId, setEditingStageId] = useState<number | null>(null);
  const [stageNameDraft, setStageNameDraft] = useState("");

  const [editingQuestionId, setEditingQuestionId] = useState<number | null>(null);
  const [addingToStageId, setAddingToStageId] = useState<number | null>(null);
  const [questionForm, setQuestionForm] = useState<QuestionForm>(EMPTY_QUESTION_FORM);

  const reload = useCallback(() => {
    getFramework(projectId).then((f) => { setFramework(f); onChange?.(); }).catch(() => setError("Could not load the framework."));
    // onChange is a fire-and-forget notification, not a reactive dependency -
    // including it would recreate `reload` (and refire the mount effect) on
    // every parent render if the caller passes an inline arrow function.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  function askConfirm(pending: PendingConfirm) {
    setConfirmState(pending);
  }

  async function handleAddStage() {
    const name = newStageName.trim();
    if (!name) return;
    setNewStageName("");
    await run(() => createFrameworkStage(projectId, name));
  }

  function startAddQuestion(stageId: number) {
    setAddingToStageId(stageId);
    setEditingQuestionId(null);
    setQuestionForm(EMPTY_QUESTION_FORM);
  }

  function startEditQuestion(q: Question) {
    setEditingQuestionId(q.id);
    setAddingToStageId(null);
    setQuestionForm(questionToForm(q));
  }

  function cancelQuestionForm() {
    setAddingToStageId(null);
    setEditingQuestionId(null);
    setQuestionForm(EMPTY_QUESTION_FORM);
  }

  async function submitAddQuestion(stageId: number) {
    if (!questionForm.level.trim() || !questionForm.text.trim() || !questionForm.ownerRole.trim()) return;
    await run(() => createFrameworkQuestion(projectId, stageId, {
      level: questionForm.level.trim(),
      text: questionForm.text.trim(),
      owner_role: questionForm.ownerRole.trim(),
      search_query: questionForm.searchQuery.trim() || undefined,
      reviewer_role: questionForm.reviewerRole.trim() || undefined,
    }));
    cancelQuestionForm();
  }

  async function submitEditQuestion(q: Question) {
    if (!questionForm.level.trim() || !questionForm.text.trim() || !questionForm.ownerRole.trim()) return;
    await run(() => updateFrameworkQuestion(projectId, q.id, {
      level: questionForm.level.trim(),
      text: questionForm.text.trim(),
      owner_role: questionForm.ownerRole.trim(),
      search_query: questionForm.searchQuery.trim() || undefined,
      reviewer_role: questionForm.reviewerRole.trim() || undefined,
      guidance: questionForm.guidance,
    }));
    cancelQuestionForm();
  }

  function startEditStageName(stageId: number, currentName: string) {
    setEditingStageId(stageId);
    setStageNameDraft(currentName);
  }

  async function submitStageName(stageId: number) {
    const name = stageNameDraft.trim();
    if (!name) return;
    await run(() => updateFrameworkStage(projectId, stageId, { name }));
    setEditingStageId(null);
  }

  function handleDeleteStage(stageId: number, stageName: string) {
    askConfirm({
      message: `Delete stage "${stageName}" and all its questions?`,
      confirmLabel: "Delete Stage",
      danger: true,
      onConfirm: () => { setConfirmState(null); run(() => deleteFrameworkStage(projectId, stageId)); },
    });
  }

  function handleDeleteQuestion(questionId: number) {
    askConfirm({
      message: "Delete this question?",
      confirmLabel: "Delete Question",
      danger: true,
      onConfirm: () => { setConfirmState(null); run(() => deleteFrameworkQuestion(projectId, questionId)); },
    });
  }

  function handleGenerate() {
    askConfirm({
      message: "This replaces every stage and question in this project's framework with an AI-drafted set from Cosmos Knowledge, and permanently deletes any client answers or self-evaluations already saved against the current questions. Continue?",
      confirmLabel: "Generate",
      danger: true,
      onConfirm: () => { setConfirmState(null); runGenerate(false); },
    });
  }

  async function runGenerate(force: boolean) {
    setGenerating(true);
    setError(null);
    try {
      const result = await generateFramework(projectId, force);
      if (!result.generated) {
        setError("Generation failed — the framework is unchanged. Try again, or check that an LLM provider is configured.");
      }
      reload();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not generate the framework.";
      if (!force && message.includes("force=true")) {
        askConfirm({
          message: `${message}\n\nThis cannot be undone. Continue anyway?`,
          confirmLabel: "Continue",
          danger: true,
          onConfirm: () => { setConfirmState(null); runGenerate(true); },
        });
      } else {
        setError(message);
      }
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
            {editingStageId === stage.id ? (
              <div className="assign-row" style={{ flex: 1 }}>
                <input type="text" autoFocus value={stageNameDraft} onChange={(e) => setStageNameDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submitStageName(stage.id)} />
                <button className="btn btn-secondary" disabled={busy} onClick={() => submitStageName(stage.id)}><i className="fa-solid fa-check"></i></button>
                <button className="btn btn-secondary" disabled={busy} onClick={() => setEditingStageId(null)}><i className="fa-solid fa-xmark"></i></button>
              </div>
            ) : (
              <span className="framework-stage-name">{stage.name}</span>
            )}
            <span className="framework-stage-actions">
              <button className="btn btn-secondary" title="Move up" disabled={busy || generating} onClick={() => run(() => updateFrameworkStage(projectId, stage.id, { action: "move_up" }))}><i className="fa-solid fa-arrow-up"></i></button>
              <button className="btn btn-secondary" title="Move down" disabled={busy || generating} onClick={() => run(() => updateFrameworkStage(projectId, stage.id, { action: "move_down" }))}><i className="fa-solid fa-arrow-down"></i></button>
              <button className="btn btn-secondary" title="Rename" disabled={busy || generating} onClick={() => startEditStageName(stage.id, stage.name)}><i className="fa-solid fa-pen"></i></button>
              <button className="btn btn-secondary" title="Delete stage" disabled={busy || generating} onClick={() => handleDeleteStage(stage.id, stage.name)}><i className="fa-solid fa-trash"></i></button>
            </span>
          </div>

          {stage.questions.map((q) => {
            const guidance = q.guidance?.[0]?.content ?? "";
            if (editingQuestionId === q.id) {
              return (
                <div className="framework-question" key={q.id}>
                  <QuestionFormFields form={questionForm} setForm={setQuestionForm} includeGuidance />
                  <div className="actions-row">
                    <button className="btn btn-secondary" onClick={cancelQuestionForm}>Cancel</button>
                    <button className="btn btn-primary" disabled={busy} onClick={() => submitEditQuestion(q)}>Save</button>
                  </div>
                </div>
              );
            }
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
                  <button className="btn btn-secondary" disabled={busy || generating} onClick={() => startEditQuestion(q)}><i className="fa-solid fa-pen"></i></button>
                  <button className="btn btn-secondary" disabled={busy || generating} onClick={() => handleDeleteQuestion(q.id)}><i className="fa-solid fa-trash"></i></button>
                </div>
                {guidance && <div className="framework-guidance"><i className="fa-solid fa-book"></i> {guidance}</div>}
              </div>
            );
          })}

          {addingToStageId === stage.id ? (
            <div className="framework-question">
              <QuestionFormFields form={questionForm} setForm={setQuestionForm} includeGuidance={false} />
              <div className="actions-row">
                <button className="btn btn-secondary" onClick={cancelQuestionForm}>Cancel</button>
                <button className="btn btn-primary" disabled={busy} onClick={() => submitAddQuestion(stage.id)}>Add Question</button>
              </div>
            </div>
          ) : (
            <button className="btn btn-secondary" disabled={busy || generating} onClick={() => startAddQuestion(stage.id)}><i className="fa-solid fa-plus"></i> Add question</button>
          )}
        </div>
      ))}

      {error && <p style={{ color: "var(--error)", marginTop: 12 }}>{error}</p>}

      {confirmState && (
        <ConfirmDialog
          message={confirmState.message}
          confirmLabel={confirmState.confirmLabel}
          danger={confirmState.danger}
          onConfirm={confirmState.onConfirm}
          onCancel={() => setConfirmState(null)}
        />
      )}
    </div>
  );
}

function QuestionFormFields({ form, setForm, includeGuidance }: { form: QuestionForm; setForm: (f: QuestionForm) => void; includeGuidance: boolean }) {
  return (
    <>
      <div className="answer-wrapper">
        <label>Level</label>
        <input type="text" value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })} placeholder="e.g. Level 3: Brand Positioning" />
      </div>
      <div className="answer-wrapper">
        <label>Question text</label>
        <textarea value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} rows={2} />
      </div>
      <div className="answer-wrapper">
        <label>Owner role</label>
        <input type="text" value={form.ownerRole} onChange={(e) => setForm({ ...form, ownerRole: e.target.value })} placeholder="e.g. Brand Manager, CMO, CEO" />
      </div>
      <div className="answer-wrapper">
        <label>Search query (optional)</label>
        <input type="text" value={form.searchQuery} onChange={(e) => setForm({ ...form, searchQuery: e.target.value })} />
      </div>
      <div className="answer-wrapper">
        <label>Reviewer role (optional)</label>
        <input type="text" value={form.reviewerRole} onChange={(e) => setForm({ ...form, reviewerRole: e.target.value })} />
      </div>
      {includeGuidance && (
        <div className="answer-wrapper">
          <label>Guidance (framework text)</label>
          <textarea value={form.guidance} onChange={(e) => setForm({ ...form, guidance: e.target.value })} rows={3} />
        </div>
      )}
    </>
  );
}
