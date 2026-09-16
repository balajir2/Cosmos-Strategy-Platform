# Design Spec: Known Gaps Cleanup — Admin Settings Auth & Manual Transcript Paste

**Date:** 2026-09-16
**Status:** Approved for planning

## Goal

Close two small, independently-tracked gaps named in `CLAUDE.md`'s "Known gaps" (Part 4) and `documentation/product/roadmap.md`, before returning to the paused GCP deployment thread:

1. `/api/admin/settings` still uses a stopgap shared-token gate instead of the real per-user `require_admin` dependency every other admin-only endpoint already uses.
2. There is no way through the API to manually supply a transcript for an audio artifact stuck at `'Transcript Needed'` status, completing its ingestion into the Engagement Knowledge Base.

These are unrelated in code but bundled into one spec/plan since both are small, low-risk "close a known gap" cleanups with no shared implementation surface.

## Non-Goals

- No changes to the LLM provider settings themselves (`platform_settings.get_active_provider`/`set_active_provider`) — only the auth gate on the two endpoints that expose them.
- No automatic re-transcription retry, no background job queue for transcription.
- No support for re-pasting or correcting a transcript after an artifact is already `'Indexed'` — this closes the fallback loop for artifacts currently stuck at `'Transcript Needed'` only. Revisit if a real need for correction surfaces later.
- No change to `transcribe_audio`'s own automatic-transcription behavior (bucket/format detection, polling) — untouched.

## Part 1: Admin Settings — Real Auth

**Current state**: `GET`/`PATCH /api/admin/settings` (`backend/main.py`) gate via `Depends(require_admin_token)` (`backend/admin_auth.py`), which checks a single shared secret in an `X-Admin-Token` header against the `ADMIN_API_TOKEN` env var. Every other admin-only endpoint (`/api/admin/users`, `/api/admin/projects`, `/api/admin/framework-knowledge`) already uses `require_admin` (`backend/auth.py`) — JWT bearer token via `get_current_user`, then an `is_admin` check, `403` if not an admin. Nothing in `frontend-react/` calls `/api/admin/settings` today, so there is no UI dependency on the old header-based scheme.

**Change**:
- `backend/main.py`: swap `Depends(require_admin_token)` → `Depends(require_admin)` on both `get_settings` and `update_settings`, and drop the now-unused `from admin_auth import require_admin_token` import.
- Delete `backend/admin_auth.py` and `tests/test_admin_auth.py` outright — once nothing references `require_admin_token`, it's dead code. This codebase's convention (per `CLAUDE.md`) is to delete unused code rather than leave it dormant "in case it's needed later."
- Rewrite `tests/test_admin_settings_endpoint.py` to use the `dependency_overrides[main.get_current_user]` pattern every other admin/project endpoint test in this suite already uses (e.g. `tests/test_admin_projects_endpoints.py`), covering: a non-admin authenticated user gets `403`, an unauthenticated request gets `401`, and the existing success/validation cases (get returns active provider, patch updates it, patch rejects an invalid provider with `400`) now authenticate as an admin user instead of sending a header.
- Documentation: remove the remaining `ADMIN_API_TOKEN`/stopgap-gate mentions from `CLAUDE.md` (Part 3's tech-stack paragraph, Part 4's endpoint table, Part 4's Known gaps, Part 5) and `documentation/product/roadmap.md`'s Admin UI checklist item. In `docs/superpowers/plans/2026-08-25-gcp-deployment-infrastructure.md`, leave the historical plan text as-is (it's a record of what was originally planned) but note in the roadmap that `ADMIN_API_TOKEN` is no longer a secret that needs provisioning when that deployment work resumes.

No schema change, no migration, no frontend change.

## Part 2: Manual Transcript Paste

**Current state**: `backend/project_knowledge_base.py`'s `transcribe_audio` returns `None` when Google Speech-to-Text isn't configured, the audio format isn't supported (mp3/wav/flac/ogg only — m4a always falls back), or the job fails — `ingest_artifact` then sets the artifact's status to `'Transcript Needed'` rather than `'Failed'`. Nothing in the API today lets that artifact move forward; it's permanently stuck unless re-uploaded as a supported format with transcription configured.

**Backend**:
- Extract a private helper in `backend/project_knowledge_base.py`:
  ```python
  def _finalize_text(rag, artifact: dict, text: str) -> dict:
      """Shared tail of the ingestion pipeline: chunk, embed, insert into
      project_kb_chunks, and update the artifact's status. Used by both the
      automatic pipeline (ingest_artifact) and the manual-transcript-paste
      path (ingest_manual_transcript) - the only difference between the two
      callers is how `text` was obtained."""
      chunks = chunk_text(text)
      if not chunks:
          return project_artifacts_db.update_artifact_status(artifact["id"], "Failed")
      embeddings = rag.embedding_model.encode(chunks)
      _insert_chunks(artifact["project_id"], artifact["id"], chunks, embeddings)
      transcript_text = text if artifact["source_format"] == "audio" else None
      return project_artifacts_db.update_artifact_status(artifact["id"], "Indexed", transcript_text=transcript_text)
  ```
  `ingest_artifact` is rewritten to call `_finalize_text(rag, artifact, text)` after obtaining `text` (from either `extract_text` or `transcribe_audio`), replacing its current inline chunk/embed/insert/status-update block. Its observable behavior (return value, status transitions, `'Failed'`-on-no-text handling) is unchanged — this is a pure refactor to share code with the new path.
- New function:
  ```python
  def ingest_manual_transcript(rag, artifact_id: int, transcript_text: str) -> dict:
      """Completes the 'Transcript Needed' fallback loop: a Consultant supplies
      the transcript by hand when automatic transcription wasn't available or
      failed. Only valid on an artifact currently in that exact status - not a
      general-purpose transcript-correction endpoint."""
      artifact = project_artifacts_db.get_artifact_by_id(artifact_id)
      if artifact is None:
          raise ValueError(f"Unknown artifact_id '{artifact_id}'")
      if artifact["status"] != "Transcript Needed":
          raise ValueError(f"Artifact {artifact_id} is not awaiting a manual transcript (status: '{artifact['status']}').")
      return _finalize_text(rag, artifact, transcript_text)
  ```
- New endpoint in `backend/main.py`, placed alongside the other `/artifacts` endpoints:
  ```python
  @app.post("/api/projects/{project_id}/artifacts/{artifact_id}/transcript")
  async def paste_artifact_transcript(
      project_id: int,
      artifact_id: int,
      payload: TranscriptPasteRequest,
      member: dict = Depends(require_consultant),
  ):
      artifact = project_artifacts_db.get_artifact_by_id(artifact_id)
      if artifact is None or artifact["project_id"] != project_id:
          raise HTTPException(status_code=404, detail="Artifact not found.")
      if not payload.transcript_text.strip():
          raise HTTPException(status_code=400, detail="transcript_text cannot be blank.")
      try:
          return await run_in_threadpool(project_knowledge_base.ingest_manual_transcript, rag, artifact_id, payload.transcript_text)
      except ValueError as e:
          raise HTTPException(status_code=400, detail=str(e))
  ```
  `TranscriptPasteRequest` is a new Pydantic model (`{transcript_text: str}`) alongside the app's other request models. `run_in_threadpool` is used because this calls into the same `SentenceTransformer.encode` the upload endpoint already runs off the event loop for.

**Frontend**:
- New `frontend-react/lib/api-client.ts` function:
  ```typescript
  export async function pasteTranscript(projectId: number, artifactId: number, transcriptText: string): Promise<ProjectArtifact> {
    const res = await authFetch(`/api/projects/${projectId}/artifacts/${artifactId}/transcript`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript_text: transcriptText }),
    });
    if (!res.ok) throw new Error(await errorDetail(res, `Failed to save transcript: ${res.status}`));
    return res.json();
  }
  ```
- On `frontend-react/app/admin/project/[caseId]/page.tsx`, each artifact row (in the existing `artifacts.map(...)` block) with `status === "Transcript Needed"` gets a "Paste Transcript" button. Clicking it reveals an inline textarea + Submit/Cancel for that row only (local per-row expanded state, not a new modal). On successful submit, replace that artifact's entry in the local `artifacts` state array with the endpoint's returned (now `Indexed`) artifact — no full list refetch needed, consistent with how `handleDeleteArtifact` already updates local state directly rather than reloading.

## Testing

- **Backend**: `tests/test_project_knowledge_base.py` gains tests for `_finalize_text` (chunks+embeds+inserts on non-empty text, sets `'Failed'` on empty/whitespace-only text) and `ingest_manual_transcript` (success path sets `'Indexed'` and stores `transcript_text`; raises `ValueError` for an unknown artifact; raises `ValueError` when the artifact's status isn't `'Transcript Needed'`). `ingest_artifact`'s existing tests must all still pass unchanged, confirming the refactor preserved behavior.
- New `tests/test_transcript_paste_endpoint.py` (or added to `tests/test_project_artifact_endpoints.py`, whichever the implementation plan finds cleaner given the existing file's size): non-Consultant/non-member → `403`; artifact belonging to a different project or unknown → `404`; artifact not in `'Transcript Needed'` status → `400`; blank `transcript_text` → `400`; success → `200` with the artifact now `'Indexed'` and `transcript_text` populated.
- **Frontend**: no test framework exists (consistent with every prior UI change in this codebase) — verified via `npm run build` plus a manual code read-through of the new per-row expand/submit state.

## Open Items

None — both parts were confirmed section-by-section during brainstorming, including the specific fork decisions (frontend UI now vs. later, one-shot-only vs. re-pasteable, and the code-reuse approach for the ingestion pipeline).
