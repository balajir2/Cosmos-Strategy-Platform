"use client";

import { useEffect, useState } from "react";
import {
  FrameworkKnowledgeSource, adminListFrameworkKnowledge, adminUploadFrameworkKnowledge, adminDeleteFrameworkKnowledge,
} from "@/lib/api-client";

export default function FrameworkKnowledgeTab() {
  const [sources, setSources] = useState<FrameworkKnowledgeSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    setLoading(true);
    adminListFrameworkKnowledge()
      .then(setSources)
      .catch(() => setError("Could not load Framework Knowledge sources."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { reload(); }, []);

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await adminUploadFrameworkKnowledge(file);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload the file.");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(source: FrameworkKnowledgeSource) {
    if (!window.confirm(`Delete "${source.filename}" from the Framework Knowledge Base?`)) return;
    setError(null);
    try {
      await adminDeleteFrameworkKnowledge(source.id);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete the source.");
    }
  }

  if (loading) {
    return <div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading Framework Knowledge...</div>;
  }

  return (
    <div>
      <div className="glass-card" style={{ padding: 20, marginBottom: 20 }}>
        <h3><i className="fa-solid fa-brain"></i> Upload Cosmos Knowledge</h3>
        <p className="dropzone-hint">Widens the shared Framework Knowledge Base every project draws from. PDF, DOCX, PPTX, TXT, MD, or XLSX only.</p>
        <label className="dropzone" style={{ display: "block", pointerEvents: uploading ? "none" : undefined, opacity: uploading ? 0.6 : 1 }}>
          <input type="file" onChange={handleFileSelected} style={{ display: "none" }} disabled={uploading} />
          <i className="fa-solid fa-cloud-arrow-up"></i>
          <p>{uploading ? "Uploading and indexing..." : <>Click to <span className="dropzone-browse">browse</span></>}</p>
        </label>
      </div>

      {error && <p style={{ color: "var(--level-1)", marginBottom: 12 }}>{error}</p>}

      {sources.length === 0 && !error && (
        <p style={{ color: "var(--text-muted)", marginBottom: 12 }}>No Cosmos Knowledge sources uploaded yet.</p>
      )}

      <div className="admin-list">
        {sources.map((s) => (
          <div className="glass-card admin-row" key={s.id}>
            <div className="admin-row-main">
              <div className="admin-row-name">{s.filename}</div>
            </div>
            <div className="admin-row-meta">
              <span className={`status-pill ${s.status === "Indexed" ? "indexed" : ""}`}>{s.status}</span>
            </div>
            <div className="admin-row-actions">
              <button className="btn btn-secondary" onClick={() => handleDelete(s)}>
                <i className="fa-solid fa-trash"></i> Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
