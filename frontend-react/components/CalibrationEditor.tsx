"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getCalibrationConcepts, addCalibrationConcept, updateCalibrationConcept, deleteCalibrationConcept,
  CalibrationConcept,
} from "@/lib/api-client";

export default function CalibrationEditor({ projectId }: { projectId: number }) {
  const [concepts, setConcepts] = useState<CalibrationConcept[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newConceptName, setNewConceptName] = useState("");
  const [busy, setBusy] = useState(false);

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
    const name = newConceptName.trim();
    if (!name) return;
    const orgDefinition = window.prompt(`This organization's definition of "${name}"`);
    if (!orgDefinition) return;
    setNewConceptName("");
    await run(() => addCalibrationConcept(projectId, name, orgDefinition));
  }

  if (!concepts) {
    return <div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading calibration concepts...</div>;
  }

  return (
    <div className="glass-card framework-card">
      <h3><i className="fa-solid fa-compass"></i> Baseline Calibration</h3>
      <p className="dropzone-hint">A handful of core concepts the client defines before their first question, scored against this organization&apos;s own definitions.</p>

      <div className="answer-wrapper">
        <label htmlFor="new-concept-input">Add concept</label>
        <div className="assign-row">
          <input id="new-concept-input" type="text" value={newConceptName} onChange={(e) => setNewConceptName(e.target.value)} placeholder="e.g. insight" />
          <button className="btn btn-secondary" onClick={handleAddConcept} disabled={busy}><i className="fa-solid fa-plus"></i> Add</button>
        </div>
      </div>

      {concepts.map((concept) => (
        <div className="framework-question" key={concept.id}>
          <div className="framework-question-text">{concept.concept_name}</div>
          <div className="framework-question-meta">
            <span className="dropzone-hint">{concept.org_definition}</span>
          </div>
          <div className="framework-question-actions">
            <button className="btn btn-secondary" disabled={busy} onClick={() => run(() => updateCalibrationConcept(projectId, concept.id, { action: "move_up" }))}><i className="fa-solid fa-arrow-up"></i></button>
            <button className="btn btn-secondary" disabled={busy} onClick={() => run(() => updateCalibrationConcept(projectId, concept.id, { action: "move_down" }))}><i className="fa-solid fa-arrow-down"></i></button>
            <button className="btn btn-secondary" disabled={busy} onClick={() => {
              const name = window.prompt("Concept name", concept.concept_name); if (!name) return;
              const orgDefinition = window.prompt("Organization's definition", concept.org_definition); if (!orgDefinition) return;
              run(() => updateCalibrationConcept(projectId, concept.id, { concept_name: name, org_definition: orgDefinition }));
            }}><i className="fa-solid fa-pen"></i></button>
            <button className="btn btn-secondary" disabled={busy} onClick={() => { if (window.confirm(`Delete "${concept.concept_name}"?`)) run(() => deleteCalibrationConcept(projectId, concept.id)); }}><i className="fa-solid fa-trash"></i></button>
          </div>
        </div>
      ))}

      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
