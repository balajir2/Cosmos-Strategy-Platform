"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getCalibrationConcepts, addCalibrationConcept, updateCalibrationConcept, deleteCalibrationConcept,
  CalibrationConcept,
} from "@/lib/api-client";
import ConfirmDialog from "./ConfirmDialog";

type PendingConfirm = { message: string; confirmLabel?: string; danger?: boolean; onConfirm: () => void };

export default function CalibrationEditor({ projectId }: { projectId: number }) {
  const [concepts, setConcepts] = useState<CalibrationConcept[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmState, setConfirmState] = useState<PendingConfirm | null>(null);

  const [newName, setNewName] = useState("");
  const [newDefinition, setNewDefinition] = useState("");

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editDefinition, setEditDefinition] = useState("");

  const reload = useCallback(() => {
    getCalibrationConcepts(projectId).then(setConcepts).catch(() => setError("Could not load calibration concepts."));
  }, [projectId]);

  useEffect(() => { reload(); }, [reload]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update calibration concepts.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddConcept() {
    const name = newName.trim();
    const orgDefinition = newDefinition.trim();
    if (!name || !orgDefinition) return;
    setNewName("");
    setNewDefinition("");
    await run(() => addCalibrationConcept(projectId, name, orgDefinition));
  }

  function startEdit(concept: CalibrationConcept) {
    setEditingId(concept.id);
    setEditName(concept.concept_name);
    setEditDefinition(concept.org_definition);
  }

  function cancelEdit() {
    setEditingId(null);
  }

  async function submitEdit(conceptId: number) {
    const name = editName.trim();
    const orgDefinition = editDefinition.trim();
    if (!name || !orgDefinition) return;
    await run(() => updateCalibrationConcept(projectId, conceptId, { concept_name: name, org_definition: orgDefinition }));
    setEditingId(null);
  }

  function handleDelete(conceptId: number, conceptName: string) {
    setConfirmState({
      message: `Delete "${conceptName}"?`,
      confirmLabel: "Delete",
      danger: true,
      onConfirm: () => { setConfirmState(null); run(() => deleteCalibrationConcept(projectId, conceptId)); },
    });
  }

  if (!concepts) {
    return <div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading calibration concepts...</div>;
  }

  return (
    <div className="glass-card framework-card">
      <h3><i className="fa-solid fa-compass"></i> Baseline Calibration</h3>
      <p className="dropzone-hint">A handful of core concepts the client defines before their first question, scored against this organization&apos;s own definitions.</p>

      <div className="answer-wrapper">
        <label htmlFor="new-concept-name">Add concept</label>
        <input id="new-concept-name" type="text" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. insight" />
      </div>
      <div className="answer-wrapper">
        <label htmlFor="new-concept-definition">This organization&apos;s definition</label>
        <div className="assign-row">
          <textarea id="new-concept-definition" value={newDefinition} onChange={(e) => setNewDefinition(e.target.value)} rows={2} />
          <button className="btn btn-secondary" onClick={handleAddConcept} disabled={busy}><i className="fa-solid fa-plus"></i> Add</button>
        </div>
      </div>

      {concepts.map((concept) => (
        <div className="framework-question" key={concept.id}>
          {editingId === concept.id ? (
            <>
              <div className="answer-wrapper">
                <label>Concept name</label>
                <input type="text" autoFocus value={editName} onChange={(e) => setEditName(e.target.value)} />
              </div>
              <div className="answer-wrapper">
                <label>Organization&apos;s definition</label>
                <textarea value={editDefinition} onChange={(e) => setEditDefinition(e.target.value)} rows={2} />
              </div>
              <div className="actions-row">
                <button className="btn btn-secondary" onClick={cancelEdit}>Cancel</button>
                <button className="btn btn-primary" disabled={busy} onClick={() => submitEdit(concept.id)}>Save</button>
              </div>
            </>
          ) : (
            <>
              <div className="framework-question-text">{concept.concept_name}</div>
              <div className="framework-question-meta">
                <span className="dropzone-hint">{concept.org_definition}</span>
              </div>
              <div className="framework-question-actions">
                <button className="btn btn-secondary" disabled={busy} onClick={() => run(() => updateCalibrationConcept(projectId, concept.id, { action: "move_up" }))}><i className="fa-solid fa-arrow-up"></i></button>
                <button className="btn btn-secondary" disabled={busy} onClick={() => run(() => updateCalibrationConcept(projectId, concept.id, { action: "move_down" }))}><i className="fa-solid fa-arrow-down"></i></button>
                <button className="btn btn-secondary" disabled={busy} onClick={() => startEdit(concept)}><i className="fa-solid fa-pen"></i></button>
                <button className="btn btn-secondary" disabled={busy} onClick={() => handleDelete(concept.id, concept.concept_name)}><i className="fa-solid fa-trash"></i></button>
              </div>
            </>
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
