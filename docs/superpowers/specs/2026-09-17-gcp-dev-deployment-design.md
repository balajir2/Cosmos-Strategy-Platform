# Design Spec: GCP Dev Deployment — Single Service + the Artifact Pipeline

**Date:** 2026-09-17 (revised 2026-09-18)
**Status:** Approved for planning

## Goal

Stand up a real, working GCP deployment of the Cosmos Strategic Capability Platform — one Cloud Run service serving both the FastAPI backend and the Next.js frontend's static export, plus (in the same pass) the already-written-but-never-applied async artifact-ingestion pipeline — in the existing `cosmos-strategy` GCP project, for **development use**, not a production pilot. This is the first time anything in this repo is actually deployed to GCP.

This spec **supersedes** `docs/superpowers/specs/2026-08-25-production-deployment-design.md`. That spec is left in place as a historical record, per this repo's established convention — not edited, not deleted. Where the two disagree, this spec wins.

## Revision History

- **2026-09-17, initial version:** two Cloud Run services (backend + frontend), a new Terraform module for both, Gemini as the LLM provider.
- **2026-09-18, revised:** collapsed to **one** Cloud Run service and switched provisioning from a new Terraform module to plain `gcloud` CLI commands, after directly discussing the tradeoffs. Both were deliberate simplifications, made explicitly aware of what they give up (see Decisions Reconsidered below) — not the default choice, an active one.

## Decisions Reconsidered (2026-09-18)

**One service, not two.** A single Cloud Run service means the frontend can't run its normal Next.js server (`next start`) without either a second process in the same container (a reverse proxy in front of two processes — more complex, not less) or building it as a **static export** instead. Static export was chosen. The complication that surfaces: two of the app's routes are dynamic path segments with arbitrary, DB-driven IDs (`/admin/project/[caseId]`, `/client/case/[caseId]/...`), and Next.js static export can't pre-generate pages for IDs it doesn't know at build time. This is resolved by converting those two route trees to read the ID from a query string instead of a path segment — a real, if mechanical and contained, frontend change (see "Frontend Static Export & Route Refactor" below). This was chosen over reverting to two services because it produces a genuinely simpler *deployed* system (one process per container, no reverse proxy) at the cost of upfront app-code changes, rather than pushing complexity into container internals.

**`gcloud` CLI, not a new Terraform module.** This reverses part of a 2026-09-09 decision (recorded in the assistant's memory) that all GCP infrastructure should be Terraform-provisioned for easy reproducibility (e.g. redeploying identically to a different GCP account later). The tradeoff, made knowingly: `gcloud` commands are simpler to write and run once, but aren't automatically reproducible — if this environment needs recreating (e.g. on a different GCP account), someone has to re-run the documented command sequence by hand, or convert to Terraform at that point (via `terraform import`, or simpler at this scale, tearing down and reapplying fresh). The **existing** `infra/terraform/artifact-pipeline/` module is unaffected by this and stays exactly as Terraform, unmodified — it's already written, already correct, and doesn't need touching. This spec's `gcloud`-provisioned resources simply feed it plain string values (a secret ID, a bucket name) as `-var` inputs, exactly as its own README already anticipated ("provisioned by the main app's own deployment work").

## Non-Goals

- **Not a production pilot.** Development-scale deployment only — see Cost & Scaling Discipline. Re-evaluate sizing, alerting, and the single-environment assumption before any real pilot traffic.
- **No custom domain.** The default `*.run.app` HTTPS URL.
- **No OpenAI or Anthropic secrets provisioned.** Only Gemini (via Vertex AI/IAM, no stored key) is wired up as the active LLM provider. Both other adapters remain fully functional in code and reachable via the admin settings panel — just not provisioned here.
- **No `RESEND_API_KEY`.** The Consultant-Initiated Client Invites feature already degrades gracefully to a copy/paste setup link without it — not worth provisioning for a dev environment.
- **`FRONTEND_BASE_URL` deferred**, even though it's now trivial (same single URL, no cross-service ordering problem left) — a one-line `gcloud run services update --update-env-vars` follow-up whenever it's actually wanted, not required for this pass.
- **No staging environment.** Single environment, named `dev` (deliberately distinct from a future real pilot's naming).
- **No Cloud Monitoring alert policies** (error rate, LLM failures) — deferred; revisit once there's real traffic to monitor. The $5 Billing Budget alert (below) is a different, cheaper mechanism that stays in scope because it targets this spec's actual motivating concern (cost surprises).
- **No GCS lifecycle/cleanup policy** for the artifacts bucket — a known, pre-existing open question, not resolved here.

## Architecture

```
                         ┌──────────────────────┐
                         │   Browser (dev use)   │
                         └──────────┬────────────┘
                                    │ HTTPS
                         ┌──────────▼───────────────────┐
                         │  cosmos-dev (Cloud Run)        │
                         │  FastAPI + StaticFiles mount   │
                         │  (Next.js static export)       │
                         │  min=0 max=2, 2Gi/2CPU          │
                         └──┬──────────┬──────────┬───────┘
                            │          │          │
              ┌─────────────┘          │          └───────────────┐
              ▼                        ▼                          ▼
   ┌─────────────────────┐  ┌──────────────────┐      ┌─────────────────────┐
   │   Neon Postgres      │  │   Vertex AI       │      │  GCS: artifacts +    │
   │  (existing, reused)  │  │   (Gemini)        │      │  transcribe-staging   │
   └───────────────────────┘  └───────────────────┘      │  buckets              │
                                                          └──────────┬───────────┘
                                                                     │ Eventarc
                                                                     ▼
                                                          ┌────────────────────────┐
                                                          │ cosmos-artifact-        │
                                                          │ processor (Cloud Run)   │
                                                          │ min=0 max=2, 2Gi/2CPU   │
                                                          │ (existing TF module)    │
                                                          └─────────────────────────┘
```

**Components:**
- **`cosmos-dev`** (Cloud Run, `gcloud`-deployed) — the FastAPI app, serving both `/api/*` routes and the Next.js static export (via a `StaticFiles` mount registered *after* every API route so it never shadows one). Built from a new multi-stage root `Dockerfile`: a Node stage runs `npm ci && npm run build` in `frontend-react/` to produce its static `out/` directory, then a Python stage copies `backend/` plus that `out/` directory. Public, `--allow-unauthenticated` (app-level auth is JWT-based, not network-level).
- **`cosmos-artifact-processor`** (Cloud Run, existing Terraform module, not yet applied) — unchanged in shape from its 2026-09-02 design, plus the scaling addition below. This spec finally supplies its external inputs (`database_url_secret_id`, `transcribe_bucket_name`, `processor_image`) — all `gcloud`-provisioned, none newly Terraform-managed.
- **Neon Postgres** — the existing local-dev database, reused as-is. No new Neon project/branch.
- **Vertex AI (Gemini)** — reached via `cosmos-backend-sa`'s own IAM identity (created by the `artifact-pipeline` Terraform module, which `cosmos-dev` also deploys *as*), no API key stored anywhere.

## Frontend Static Export & Route Refactor

Required for the single-service architecture. All mechanical, no behavior changes beyond how an ID gets read:

- `next.config.ts` gains `output: "export"`.
- Three page files move out of their `[caseId]` dynamic-segment folders into flat routes, each swapping `useParams()` for `useSearchParams()` and reading the id from a query string instead of a path segment:
  - `app/admin/project/[caseId]/page.tsx` → `app/admin/project/page.tsx`
  - `app/client/case/[caseId]/page.tsx` → `app/client/case/page.tsx`
  - `app/client/case/[caseId]/chat/page.tsx` → `app/client/case/chat/page.tsx` (its sibling `chat.module.css` moves with it)
- Each moved page's own internal `router.push`/`router.replace` calls (self-navigation to a sibling route) switch from building a path segment to building a query string.
- Four components import the moved `chat.module.css` by path and need that import updated: `StageSidebar.tsx`, `MicButton.tsx`, `IosDictationHint.tsx`, `ChatMessageBubble.tsx`.
- Two `<Link href>` call sites switch from path-building to query-string-building: `app/page.tsx:56` (`/admin/project/${p.id}` → `/admin/project?id=${p.id}`) and `app/client/page.tsx:51` (`/client/case/${p.id}` → `/client/case?id=${p.id}`).
- `backend/main.py` gains one `StaticFiles(directory=..., html=True)` mount at `/`, added after every existing `@app.*` route registration.

## Provisioning (gcloud CLI, one-time setup)

No new Terraform. In order:

1. **Enable APIs**: `run.googleapis.com`, `artifactregistry.googleapis.com`, `secretmanager.googleapis.com`, `aiplatform.googleapis.com` (the `artifact-pipeline` module enables its own required APIs — storage, eventarc, speech, pubsub — when applied; enabling here too is harmless/idempotent).
2. **Artifact Registry repo**: `cosmos` (Docker format).
3. **Secrets**: `DATABASE_URL`, `JWT_SECRET_KEY` — both created from the values already in the repo's local `.env` (reusing the existing database, not shown/echoed anywhere in the plan or its output).
4. **Transcribe-staging bucket**: `cosmos-transcribe-dev` (a new bucket; the `artifact-pipeline` module takes its name as an input but doesn't create it — see that module's `main.tf` comment).
5. **Build + push the processor image** (`backend/processor_main.py`) — this service has never had a Dockerfile; a new one is added (`backend/processor.Dockerfile` or similar) alongside this work, since `artifact-pipeline`'s `processor_image` variable requires an image that already exists in Artifact Registry before `terraform apply` can succeed.
6. **`terraform apply` the existing, unmodified `infra/terraform/artifact-pipeline/` module** (its own one-time state-bucket prerequisite from its README applies here too), passing `project_id=cosmos-strategy`, `env=dev`, `processor_image=<step 5's image>`, `database_url_secret_id=DATABASE_URL`, `transcribe_bucket_name=cosmos-transcribe-dev`. This creates the artifacts bucket, `cosmos-backend-sa`, `cosmos-processor-sa`, their IAM bindings, the processor Cloud Run service, and the Eventarc trigger.
7. **Grant `cosmos-backend-sa` two more roles** (not part of the Terraform module, since that module only knows about GCS access): `secretmanager.secretAccessor` on the two secrets from step 3, and project-level `aiplatform.user` for Vertex AI.
8. **Build + push the `cosmos-dev` image** (the multi-stage Dockerfile described above).
9. **Deploy `cosmos-dev`**, running *as* `cosmos-backend-sa` (created in step 6 — fully deterministic email, `cosmos-backend-sa@cosmos-strategy.iam.gserviceaccount.com`, no need to look up a Terraform output), with `--set-secrets` for the two secrets, `--set-env-vars` for `GCP_PROJECT_ID=cosmos-strategy`, `GCP_LOCATION=us-central1`, `GCS_ARTIFACTS_BUCKET=cosmos-artifacts-dev`, `GCS_TRANSCRIBE_BUCKET=cosmos-transcribe-dev`, and the scaling/sizing from below.
10. **Run migrations + set the active provider**: `python backend/database.py` against the deployed `DATABASE_URL`, then one idempotent `UPDATE platform_settings SET active_llm_provider = 'gemini' WHERE id = 1;` so the environment comes up already on Gemini.
11. **Billing Budget**: `gcloud billing budgets create`, $5/month threshold, email alert, tied to `cosmos-strategy`'s existing billing account.

## Cost & Scaling Discipline

Prompted directly by a prior incident (an Eventarc self-retrigger loop that repeatedly reprocessed the same file) and the fact that this is unfunded, personal-account work. **The specific bug that caused that incident is already fixed in the code that exists today** (`backend/processor_main.py:67-73` returns `200 skipped` for the processor's own `processed/`/`failed/` writes instead of raising — which is what stops Eventarc from retrying; a status-based idempotency guard at line 84 covers genuine re-deliveries too; every code path in that file returns `200`, never a `5xx` Eventarc would retry). This spec adds defense-in-depth on top of that fix, not a replacement for it:

- **Explicit `min-instances=0` on both Cloud Run services** — `cosmos-dev` (a `gcloud run deploy` flag) and `cosmos-artifact-processor` (a `scaling { min_instance_count = 0 }` block added to its existing Terraform resource, which currently has no scaling block at all). True scale-to-zero everywhere; cold starts are an accepted dev-scale tradeoff.
- **Explicit `max-instances=2` on both** — the processor currently has no cap and would otherwise inherit Cloud Run's default ceiling of 100. Even a genuine event storm can't scale wide.
- **No "always allocate CPU"** on either service — default Cloud Run billing (CPU only during active request handling).
- **The $5 Billing Budget** (Provisioning step 11).

## Secrets & IAM Summary

| Secret/Identity | Holds / Grants | Created by |
|---|---|---|
| `DATABASE_URL` (Secret Manager) | Neon connection string, reused from local `.env` | `gcloud` (step 3) |
| `JWT_SECRET_KEY` (Secret Manager) | JWT signing key, reused from local `.env` | `gcloud` (step 3) |
| `cosmos-backend-sa` | GCS grants (from Terraform) + `secretmanager.secretAccessor` + `aiplatform.user` (from `gcloud`, step 7) | `artifact-pipeline` Terraform module; `cosmos-dev` deploys *as* this identity |
| `cosmos-processor-sa` | Unchanged from the existing module | `artifact-pipeline` Terraform module |

No `ADMIN_API_TOKEN`. No `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`. No separate frontend service account — there's only one service now.

## CI/CD

`.github/workflows/ci.yml` (tests) is untouched. A new `.github/workflows/deploy.yml`, triggered on push to `main`, gated by a GitHub `dev` environment manual-approval rule:

1. Build + push the `cosmos-dev` image (multi-stage: Node build, Python runtime).
2. Run migrations + the Gemini-provider update (Provisioning step 10).
3. `gcloud run deploy cosmos-dev --image ...` (updates the existing service in place — the one-time `gcloud` setup above isn't re-run by CI, only the image/deploy step is).
4. Optionally, if `backend/processor_main.py` or any module it imports changed: build + push a new processor image and `gcloud run deploy cosmos-artifact-processor --image ...` directly (not re-running `terraform apply` on every deploy — Terraform's job was the one-time resource/IAM/trigger setup in step 6; routine image updates go through plain `gcloud`, the same as `cosmos-dev`).

Auth via Workload Identity Federation (a WIF pool/provider + a `cosmos-deploy-sa` granted `run.developer`/`artifactregistry.writer`/`iam.serviceAccountUser` on `cosmos-backend-sa` — all `gcloud`-created, no downloaded JSON keys).

## Open Items / Dependencies

- `GITHUB_REPO` for the WIF provider's attribute condition is `balajir2/Cosmos-Strategy-Platform` (confirmed from the repo's own git remote).
- The GitHub `dev` environment's manual-approval rule and branch-protection "required check" settings are manual GitHub UI steps — not something `gcloud` or this repo's code can configure.
- The `gcloud billing budgets create` command requires the authenticated identity to hold a billing-account-level role (e.g. Billing Account Costs Manager), not just project-level Owner/Editor — separate from every other permission this spec needs, which are all project-scoped. If it fails for a permissions reason, the fallback is creating the $5 budget once by hand in the Billing console.
- This environment is **not** reproducible via a single command the way a Terraform-based one would be — recreating it (e.g. on a different GCP account later) means re-running the documented `gcloud` sequence above by hand, or converting to Terraform at that point.
