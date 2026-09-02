# Design Spec: Async Artifact Ingestion Pipeline (Engagement Knowledge Base)

**Date:** 2026-09-02
**Status:** Approved for planning

## Goal

Replace today's synchronous, in-memory-only artifact ingestion (`backend/project_knowledge_base.py`'s `ingest_artifact`, called inline on the upload request) with a decoupled pipeline: a Consultant's uploaded document/audio file lands in a `raw/` GCS folder, an event-triggered processing engine vectorizes it into the existing `project_kb_chunks` (Neon/`pgvector`) table, and the original file is moved to a `processed/` folder where it stays until the Consultant explicitly deletes it (which cascades to both the GCS object and the Neon vector rows). No file bytes should be left sitting in application memory or local disk outside of the brief window each service actively handles them. All GCP resources this introduces are provisioned via a single Terraform module so the whole stack can be redeployed into a different GCP account (e.g. moving from a dev account to the corporate account) in one `terraform apply`.

Expands supported file types from today's PDF/DOCX/PPTX/TXT/audio to also include `.md` and `.xlsx`.

## Non-Goals

- **Not migrating existing artifacts.** Today's `project_artifacts` rows have no original file bytes stored anywhere (by design — see `CLAUDE.md` Part 5, Phase C). There is nothing to backfill into `raw/`/`processed/`; this pipeline applies to uploads going forward only.
- **Not building automatic retry on failure.** A failed artifact moves to `failed/` and is marked `Failed`; the Consultant deletes it and re-uploads. No job queue, no exponential backoff — consistent with this codebase's existing "synchronous for now" / no-background-job-queue philosophy, just relocated to a different trigger mechanism.
- **Not building direct browser-to-GCS upload.** The backend continues to relay the multipart upload from the browser (streamed straight into `raw/`, never touching local disk) rather than issuing signed URLs for the browser to PUT directly. Keeps the existing frontend upload widget and server-side validation (extension, 50MB cap) unchanged.
- **Not retaining originals in local/dev mode.** When `GCS_ARTIFACTS_BUCKET` is unset (local dev, CI), ingestion runs exactly as it does today — inline, in-memory, original bytes discarded, nothing persisted to `processed/`. Only deployed environments (with the bucket configured) retain originals.
- **Not supporting legacy binary Office formats** (`.doc`, `.ppt`, `.xls`) — only modern Office Open XML (`.docx`, `.pptx`, `.xlsx`), matching the existing `.docx`/`.pptx`-only support.
- **Not building the main app's own Cloud Run deployment** (Tasks 1-4/6-7 of the still-unbuilt `docs/superpowers/plans/2026-08-25-gcp-deployment-infrastructure.md`). This spec's Terraform module is written to stand alone and to compose cleanly with that work later, not to replace or block on it.

## Architecture & Data Flow

```
Browser (Consultant)
   │  POST /api/projects/{id}/artifacts (multipart)
   ▼
FastAPI backend (existing service)
   1. validate (extension incl. .md/.xlsx, 50MB cap) — as today
   2. INSERT project_artifacts row, status='Queued'
   3. stream bytes → gs://cosmos-artifacts-{env}/raw/{project_id}/{artifact_id}/{filename}
      (no local temp file; bytes held only for the duration of the streaming upload)
   4. return 202 with the artifact row
   ▼
GCS bucket: cosmos-artifacts-{env}
   raw/{project_id}/{artifact_id}/{filename}        ← triggers Eventarc (raw/ prefix only)
   processed/{project_id}/{artifact_id}/{filename}  ← final home; kept until Consultant deletes
   failed/{project_id}/{artifact_id}/{filename}      ← final home for failed jobs
   │  object-finalized event, raw/ prefix filter
   ▼
Eventarc trigger "cosmos-artifact-raw-trigger" → invokes (private, Eventarc-SA-only) Cloud Run
service "cosmos-artifact-processor"
   1. idempotency guard: if project_artifacts.status is already terminal/Processing, no-op (200)
   2. set status='Processing'
   3. download object into memory (no local disk)
   4. extract_text() / transcribe_audio() — same functions as today, extended for .md/.xlsx
   5. chunk + embed (same SentenceTransformer model)
   6. INSERT project_kb_chunks rows in Neon
   7. copy object raw/ → processed/ (or → failed/ on error); delete the raw/ copy
   8. UPDATE project_artifacts.status ('Indexed' / 'Transcript Needed' / 'Failed')
      + gcs_object_path
   ▼
Frontend polls GET /api/projects/{id}/artifacts every ~3s while any artifact is
Queued/Processing; stops once none are.
```

**Delete (cascade):** `DELETE /api/projects/{id}/artifacts/{artifact_id}` (existing endpoint, Consultant-only) now also deletes the GCS object at the artifact's current `gcs_object_path` (`processed/...` or `failed/...`) before removing the `project_artifacts` row (whose delete still FK-cascades `project_kb_chunks` as today). A GCS delete failure surfaces as `500` rather than silently leaving an orphaned blob.

**Local / CI dual-mode:** governed by whether `GCS_ARTIFACTS_BUCKET` is set (same convention as the existing `GCS_TRANSCRIBE_BUCKET`).
- **Set** (deployed envs) → the flow above; upload endpoint streams to `raw/` and returns fast; the separate `cosmos-artifact-processor` service does the rest.
- **Unset** (local dev, CI, the 345-test pytest suite) → `ingest_artifact()` is called inline in the upload request handler exactly as it is today (via the existing threadpool trick), the response is synchronous, and no GCS/Eventarc/second-service involvement occurs at all. `gcs_object_path` stays `null` and no original bytes are persisted — this preserves the codebase's existing "runs fully offline" guarantee unchanged.

`ingest_artifact()`'s core logic (extract → chunk → embed → insert) is untouched and shared by both modes; the only new code is the streaming-to-`raw/` step, the small processor service wrapping the same core logic behind an Eventarc-invoked HTTP handler, and the move-to-`processed/`-or-`failed/` + status/path update step.

## Idempotency & Edge Cases

- **Duplicate Eventarc delivery** (at-least-once semantics): the processor checks `project_artifacts.status` before doing any work; if it's already `Processing`/`Indexed`/`Transcript Needed`/`Failed`, it no-ops and returns `200` rather than double-embedding.
- **Filename collisions within a project:** the GCS path includes the server-generated `artifact_id`, so two same-named files never collide in the bucket even though they'd collide on filename alone.
- **Delete during in-flight processing:** if a Consultant deletes an artifact while it's `Queued`/`Processing`, the delete removes the DB row and whatever GCS object currently exists. The in-flight processor checks whether its `project_artifacts` row still exists before writing its final status update; if it's gone, the processor deletes whatever it just wrote to `processed/`/`failed/` and exits without resurrecting the row.
- **`raw/`-prefix-only Eventarc filter** prevents an infinite loop — writes to `processed/`/`failed/` do not re-trigger the processor.

## Data Model

`project_artifacts` gains two changes (no new tables — a strict 1:1 between an artifact and its processing job means the existing row is enough):
- New status value **`Queued`** (set on insert, before the processor picks it up). Existing values (`Processing`, `Indexed`, `Transcript Needed`, `Failed`) are unchanged in meaning.
- New nullable column **`gcs_object_path`** (`TEXT`) — the object's current location (`raw/...`, `processed/...`, or `failed/...`), updated at each move; `null` in local/dev mode where nothing is persisted to GCS at all.

## File-Type Support

- **`.md`** — treated exactly like `.txt`: decode as UTF-8, feed into the existing paragraph-based `chunk_text()` unchanged. Markdown syntax is left in the chunk text rather than stripped (still meaningful retrieval signal; stripping is unnecessary complexity for this scope).
- **`.xlsx`** — new extractor (`openpyxl`, new dependency). Per sheet: read the header row as column labels; render each subsequent row as `"Col1: val1, Col2: val2, ..."`; pack consecutive rows into ~1000-char chunks using the same budget as `chunk_text()`'s `max_chunk_chars`, never splitting a row across two chunks. This batched-row approach was chosen over one-chunk-per-row (too many embeddings/Neon rows for wide spreadsheets — worse on both compute and storage) and over one-chunk-per-sheet (loses row-level retrieval precision and gets blindly char-split mid-row by the generic splitter). Empty sheets/rows are skipped.

## GCP Infrastructure & Naming

All resources are provisioned by a Terraform module at `infra/terraform/artifact-pipeline/`, parameterized by `project_id`, `region`, and `env` — moving to a different GCP account (e.g. the corporate account) is `terraform apply -var-file=corporate.tfvars` against that module, no manual console steps.

| Resource | Name |
|---|---|
| Artifact bucket | `cosmos-artifacts-{env}` |
| Terraform state bucket | `cosmos-tfstate-{env}` |
| Eventarc trigger | `cosmos-artifact-raw-trigger` |
| Processor Cloud Run service | `cosmos-artifact-processor` |
| Processor service account | `cosmos-processor-sa` |
| Backend service account | `cosmos-backend-sa` |

- **Bucket**: `cosmos-artifacts-{env}`, same project/region as the (future) main app Cloud Run deployment, to keep GCS↔Cloud Run traffic same-region (free, no egress). Uniform bucket-level IAM, no per-object ACLs.
- **IAM (conditional bindings on the bucket, expressed in Terraform)**: `cosmos-backend-sa` gets `roles/storage.objectCreator` scoped to `raw/*` only (via IAM condition on `resource.name.startsWith(...)`) plus `roles/storage.objectAdmin` scoped to `processed/*` and `failed/*` (needed for delete-cascade). `cosmos-processor-sa` gets read+write across all three prefixes, Neon access via the existing `DATABASE_URL` Secret Manager entry, and Speech-to-Text API access. Neither the bucket nor either service account is publicly readable.
- **Eventarc trigger** `cosmos-artifact-raw-trigger`: filtered to the `raw/` path prefix; invokes `cosmos-artifact-processor` with `roles/run.invoker` granted only to Eventarc's own service agent — the processor has no public ingress.
- **Secrets**: reuses the same Secret Manager entries the main app already depends on (`DATABASE_URL`, LLM/embedding config) rather than duplicating them.
- **State backend**: `cosmos-tfstate-{env}`, a small dedicated bucket created once as a documented manual prerequisite (Terraform can't provision the bucket that holds its own state).
- This module is independent of, but designed to compose with, the still-unbuilt main-app Terraform/deployment work (Tasks 1-4/6-7 of `docs/superpowers/plans/2026-08-25-gcp-deployment-infrastructure.md`) — same `project_id`/`region`/service-account conventions, not a competing pattern.

## Cost Estimate

Scoped to only the new components above (bucket, Eventarc, processor service, Speech-to-Text) — not Neon or the main app's own hosting, which are separate line items. Assumes same-region deployment (no egress charge between GCS and Cloud Run) and a document-heavy corpus with modest file counts per project (not millions of tiny objects).

At **50GB per project, 4 new projects/quarter, originals retained until deleted** (so GCS storage accumulates rather than resetting monthly):

| | Cumulative stored | Monthly GCS storage cost (@ $0.020/GB/mo) |
|---|---|---|
| End of Q1 | 200GB | ~$4/mo |
| End of Q2 | 400GB | ~$8/mo |
| End of Q3 | 600GB | ~$12/mo |
| End of Q4 | 800GB | ~$16/mo |

GCS operations, Cloud Run processor compute, and Eventarc/Pub·Sub all round to **~$0-1/month** at this volume — comfortably inside GCP's free tiers (180k vCPU-sec + 360k GiB-sec/month for Cloud Run; ~10GiB/month for Eventarc's underlying Pub/Sub events). If any of the 50GB/project is audio, Speech-to-Text adds a **one-time** (not recurring) transcription cost of $0.016/min at upload time — e.g. ~5GB of compressed audio (~83 hours) ≈ $80/project, once.

**Bottom line**: roughly $4-5/month starting out, growing to ~$16-17/month by end of year one at this pace — essentially all GCS storage — plus a one-time per-project bump if there's meaningful audio content.

## Backend Changes

- `backend/project_knowledge_base.py`: add `extract_text_from_md`/`extract_text_from_xlsx` extractors; extend `_EXTRACTORS`/`infer_source_format`. `ingest_artifact()` core logic unchanged.
- `backend/project_artifacts_db.py`: add `gcs_object_path` column + `Queued` status; a new `update_artifact_status(..., gcs_object_path=...)` variant.
- New module `backend/gcs_artifact_storage.py`: streaming upload to `raw/`, copy-and-delete move to `processed/`/`failed/`, delete-by-path — used by both the upload endpoint (write to `raw/`) and the delete endpoint (remove from `processed/`/`failed/`).
- New service, `cosmos-artifact-processor` (separate deploy from the main FastAPI app, own `main.py`-equivalent entrypoint): Eventarc-invoked HTTP handler that parses the GCS event payload for `project_id`/`artifact_id`, applies the idempotency guard, calls `ingest_artifact()`, and performs the move + status update.
- `backend/main.py`'s upload endpoint: branch on `GCS_ARTIFACTS_BUCKET` presence (stream-to-raw-and-return-202 vs. today's inline call) as described in Data Flow above. Delete endpoint extended for the GCS cascade.

## Frontend Changes

- Artifacts panel: after upload, poll `GET /api/projects/{id}/artifacts` (~3s interval) while any artifact for the project is `Queued`/`Processing`; stop once none are. Status badge gains a `Queued` state alongside the existing ones.
- Delete button UX unchanged — cascade reaching GCS is invisible to the Consultant.
- No new endpoints required.

## Testing

Offline-first, matching this codebase's existing philosophy (the 345-test suite runs with zero external services):
- New unit tests for `.md`/`.xlsx` extraction (mirroring existing `extract_text_from_pdf`/`_docx`/`_pptx` tests) and the batched-row Excel chunker (row never split, chunk-size budget respected, empty-row/sheet handling).
- `ingest_artifact()`'s existing test coverage carries forward unchanged.
- Local/inline-mode upload endpoint tests continue to pass as-is (CI's default mode, no `GCS_ARTIFACTS_BUCKET` set).
- New deployed/streaming-mode tests using a mocked GCS client (same mocking pattern already used for the existing `google.cloud.storage`/`speech` audio-transcription tests) covering: correct `raw/{project_id}/{artifact_id}/{filename}` path, `Queued` status, no local disk writes.
- New processor-service tests: given a fake GCS event payload, verify it calls `ingest_artifact()`, moves the object to the right prefix on success/failure, and updates status/`gcs_object_path` correctly — including the idempotency-guard no-op case.
- Extend the existing delete-artifact test to assert the (faked) GCS object is deleted alongside `project_kb_chunks` rows.
- No live GCP account required anywhere in this suite.

## Open Items

None — all fork decisions (trigger model, retention policy, compute choice, Excel chunking strategy, upload path, local/dev fallback, IaC tool, naming convention) were confirmed with the product owner before this spec was written.
