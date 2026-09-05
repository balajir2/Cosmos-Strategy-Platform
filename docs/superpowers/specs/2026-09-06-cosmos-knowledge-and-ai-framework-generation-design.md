# Design Spec: Cosmos Knowledge Uploads & AI Framework Generation

**Date:** 2026-09-06
**Status:** Approved for planning

## Goal

Two linked sub-projects, both under the roadmap's "Cosmos-Owned Content Repositories" section (`documentation/product/roadmap.md`, added 2026-09-05):

- **Sub-project A — Cosmos Knowledge Uploads**: today the shared Framework Knowledge Base (`framework_kb_chunks`) is populated only by `rag_engine.py`'s one-time startup ingestion of two bundled PDFs in `archives/`. There is no admin-facing way to add to it. This gives a SystemAdmin an upload/list/delete surface to widen that shared corpus with more of Cosmos's own source material (decks, guides, case material).
- **Sub-project B — AI Framework Generation**: uses that widened corpus to let a `diy_self_serve` project get a fully AI-drafted framework (stages + questions) instead of the plain template clone every project gets today, closing the concrete gap DIY self-serve mode has had since it was documented (2026-09-05) with no real behavior behind it. A Consultant can also trigger this on demand for any project, and always retains full edit/review authority over the result — no new reviewer role.

A is a prerequisite for B (B's generation quality depends on A's corpus existing), but A stands alone as a useful, smaller change even before B exists.

## Non-Goals

- **Not building a review/approval workflow beyond a provenance badge.** AI-drafted questions get a permanent `ai_generated` flag, not a separate reviewed/unreviewed lifecycle with a worklist — a Consultant edits them through the exact same Framework Authoring Mode endpoints as any other question.
- **Not supporting audio uploads for Cosmos Knowledge.** Only pdf/docx/pptx/txt/md/xlsx — Cosmos source material is decks and documents, not raw meeting recordings the way customer engagement artifacts are.
- **Not building an async GCS pipeline for framework knowledge uploads.** This is a low-volume admin action, not a customer-facing upload path under load concerns — synchronous inline ingestion (the same model Engagement KB artifacts used before the 2026-09-02 async pipeline) is sufficient.
- **Not changing `search()`/`search_merged()`'s query shape.** Both already `SELECT` whatever rows exist in `framework_kb_chunks`; widened rows with `NULL` phase/slide_number flow through unchanged.
- **Not touching the two legacy startup-seeded PDFs' ingestion path** (`rag_engine.ingest_pdfs`) — it keeps writing `phase`/`slide_number`-populated rows exactly as today. The new upload path is additive, not a replacement.
- **Not generalizing delivery-mode-specific behavior beyond `diy_self_serve`.** `consultant_guided_async` and `live_online` project creation are unaffected by sub-project B.

## Architecture & Data Flow — Sub-project A (Cosmos Knowledge Uploads)

```
SystemAdmin (Admin UI, new "Framework Knowledge" tab)
   │  POST /api/admin/framework-knowledge (multipart)
   ▼
FastAPI backend
   1. validate (extension: pdf/docx/pptx/txt/md/xlsx; 50MB cap)
   2. INSERT framework_kb_sources row, status='Processing'
   3. run_in_threadpool: extract_text() + chunk_text() (reused from
      project_knowledge_base.py, unchanged) → embed (same SentenceTransformer
      rag_engine.py already loads) → INSERT framework_kb_chunks rows
      (source_id=<new row>, phase=NULL, slide_number=NULL, source_file=filename)
   4. UPDATE framework_kb_sources.status → 'Indexed' / 'Failed'
   5. return the source row
   ▼
GET /api/admin/framework-knowledge      → list sources + status
DELETE /api/admin/framework-knowledge/{source_id}
   → DELETE framework_kb_sources row; framework_kb_chunks rows cascade via FK
```

Original file bytes are never persisted — same policy as the Engagement KB — only extracted text survives, embedded into `framework_kb_chunks`.

## Architecture & Data Flow — Sub-project B (AI Framework Generation)

```
Trigger 1 (automatic): POST /api/projects with delivery_mode="diy_self_serve"
   1. clone_process(template) — unchanged, atomic, fast; every project still
      gets a working framework immediately, regardless of delivery_mode
   2. projects_db.create_project(...) — unchanged
   3. transaction commits, response would normally return here
   4. best-effort, own try/except: generate_framework_from_knowledge(project)
      — failure here does NOT fail project creation or roll back the clone

Trigger 2 (manual): POST /api/projects/{id}/framework/generate (Consultant-only)
   → generate_framework_from_knowledge(project) — same function, any delivery mode,
     the retry path if automatic generation failed or was never attempted

generate_framework_from_knowledge(project):
   1. retrieve broad context from framework_kb_chunks (no project_id filter —
      this reads the shared KB): one query per existing template stage name
      (e.g. "SWOT", "Opportunity Analysis") plus one query on
      project.industry_context itself, top_k=10 each, de-duplicated by chunk
      id — reusing rag_engine.search() as-is, just called several times
      rather than once. Anchoring on the template's own stage names keeps the
      draft's structure recognizable even though its questions are new.
   2. prompt the active LLM provider (backend/llm_providers/, same abstraction
      generate_comparative_benchmarks uses) for a full stage/question draft,
      returned as structured JSON matching framework_db.py's existing
      add_stage/add_question shape
   3. on success: DELETE the project's current (template-cloned) stages/
      questions, INSERT the AI-drafted ones via add_stage/add_question,
      each question flagged ai_generated=true
   4. on any failure (LLM error, malformed JSON, no provider configured):
      leave the current framework untouched, unflagged — a project is never
      left without a working framework
```

Review/editing the result stays entirely inside the existing Consultant-only Framework Authoring endpoints — no new role, no new permission model.

## Data Model

- `framework_kb_chunks`: `phase` and `slide_number` become nullable (`ALTER COLUMN ... DROP NOT NULL`). Add nullable `source_id BIGINT REFERENCES framework_kb_sources(id) ON DELETE CASCADE`. The existing `UNIQUE (source_file, slide_number)` constraint is dropped and not replaced — uploaded rows have `slide_number=NULL`, and multiple `NULL`s don't violate uniqueness in Postgres anyway, but the constraint no longer means anything meaningful once `slide_number` is optional.
- New table `framework_kb_sources` (mirrors `project_artifacts`'s shape, minus the `purpose` field, which doesn't apply here):
  ```sql
  CREATE TABLE framework_kb_sources (
      id BIGSERIAL PRIMARY KEY,
      filename TEXT NOT NULL,
      source_format TEXT NOT NULL CHECK (source_format IN ('pdf', 'docx', 'pptx', 'txt', 'md', 'xlsx')),
      status TEXT NOT NULL DEFAULT 'Processing' CHECK (status IN ('Processing', 'Indexed', 'Failed')),
      uploaded_by BIGINT NOT NULL REFERENCES users(id),
      uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  ```
- `questions` gains `ai_generated BOOLEAN NOT NULL DEFAULT false`.
- `ProjectCreateRequest` (`backend/main.py`) gains `delivery_mode: Optional[str] = None`, passed through to `projects_db.create_project` (defaults to `consultant_guided_async` at the DB level exactly as it does for `PATCH` today — no change needed to the column's existing default/CHECK).
- All schema changes applied via the existing idempotent-migration pattern in `database.init_db` (`ADD COLUMN IF NOT EXISTS`, `DROP CONSTRAINT IF EXISTS` / re-add, matching the `delivery_mode` and `gcs_object_path` precedents).

## Backend Changes

- New `backend/framework_knowledge_db.py`: CRUD for `framework_kb_sources`, mirroring `project_artifacts_db.py`'s `_SELECT_COLUMNS` pattern.
- New ingestion function (in `rag_engine.py` or a small new module) reusing `project_knowledge_base.extract_text`/`chunk_text` unchanged, writing into `framework_kb_chunks` with `source_id`/`phase=NULL`/`slide_number=NULL`.
- Three **SystemAdmin-only** (`require_admin`) endpoints: `POST /api/admin/framework-knowledge`, `GET /api/admin/framework-knowledge`, `DELETE /api/admin/framework-knowledge/{source_id}` — same `400`/`403`/`413` pattern as the Engagement KB artifact endpoints.
- `backend/framework_db.py`: new `generate_framework_from_knowledge(project)` function as described above; reuses `add_stage`/`add_question` for insertion so sequencing/guidance-row creation stays consistent with manual authoring.
- `POST /api/projects/{id}/framework/generate` — new Consultant-only endpoint (manual trigger).
- `POST /api/projects` (`create_project` in `main.py`): accepts `delivery_mode`, calls `generate_framework_from_knowledge` as a best-effort post-commit step when `delivery_mode == "diy_self_serve"`.

## Frontend Changes

- **Admin `/admin` page**: new "Framework Knowledge" tab (parallel to Users/Projects) — upload dropzone, source list with status/delete.
- **New Project form** (SystemAdmin): gains the `delivery_mode` dropdown (previously only on the Consultant's post-creation project setup page).
- **Framework editor** (Consultant, project setup page): a "Generate Framework from Cosmos Knowledge" button calling the manual endpoint; each `ai_generated` question in the stage/question grid gets a small "AI-drafted" badge — visual only, doesn't block editing or reordering.

## Error Handling

- Upload endpoints follow the exact `400`/`403`/`413` pattern already used for Engagement KB artifacts.
- `generate_framework_from_knowledge` never raises past its own boundary — LLM errors, malformed JSON, and "no provider configured" are all caught internally, logged, and treated as "leave the existing framework as-is," returning `False`. Neither `POST /api/projects` nor `POST /api/projects/{id}/framework/generate` can 500 because of a generation failure; the latter returns `{"generated": bool, "framework": <same shape GET /api/projects/{id}/framework returns>}` so the frontend can distinguish "AI draft applied" from "still on the template, try again" without inferring it from the `ai_generated` flags itself.

## Testing

Offline-first, matching this codebase's existing philosophy:
- `test_framework_knowledge_db.py` / `test_framework_knowledge_endpoints.py`: upload/list/delete, admin-only gating, unsupported-format/size-limit cases — mirrors the existing `project_artifacts_db`/artifact-endpoint test shape.
- `test_framework_generation.py` (or similar): successful AI draft replaces the template and flags questions `ai_generated=true`; LLM failure leaves the template intact with `ai_generated=false`; malformed LLM JSON is treated the same as a provider error.
- Project-creation tests: `delivery_mode="diy_self_serve"` triggers generation automatically (mocked LLM); `consultant_guided_async`/`live_online`/omitted do not.
- Endpoint test: `POST /api/projects/{id}/framework/generate` is Consultant-only, works regardless of the project's current `delivery_mode`.
- No live GCP account or LLM provider required anywhere in this suite — same mocking pattern already used for `generate_comparative_benchmarks`'s provider-abstraction tests.

## Open Items

None — all fork decisions (upload access, file types, ingestion mode, schema shape, generation trigger and entry point, review-flag semantics, review authority) were confirmed with the product owner before this spec was written.
