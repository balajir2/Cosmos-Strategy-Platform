# Design Spec: GCP Dev Deployment — Backend, Frontend, and the Artifact Pipeline

**Date:** 2026-09-17
**Status:** Approved for planning

## Goal

Stand up a real, working GCP deployment of the Cosmos Strategic Capability Platform — the FastAPI backend, the Next.js frontend, and (in the same pass) the already-written-but-never-applied async artifact-ingestion pipeline — in the existing `cosmos-strategy` GCP project, for **development use**, not a production pilot. This is the first time anything in this repo is actually deployed to GCP.

This spec **supersedes** `docs/superpowers/specs/2026-08-25-production-deployment-design.md` in scope and a few concrete decisions (Terraform instead of raw `gcloud` CLI, no `ADMIN_API_TOKEN`, a two-service split instead of one, Gemini instead of Anthropic, explicit scale-to-zero discipline). The 2026-08-25 spec is left in place as a historical record, per this repo's established convention — not edited, not deleted. Where the two disagree, this spec wins.

## Context: why this differs from the 2026-08-25 spec

That spec was written before several things existed or changed:
- **Phase A/B/C, the LLM provider abstraction, and the admin auth cleanup have all since landed.** `ADMIN_API_TOKEN` no longer exists anywhere in the code (removed 2026-09-17, Known Gaps Cleanup) — `/api/admin/settings` now uses the same JWT-based `require_admin` dependency as every other admin endpoint.
- **The frontend migrated to Next.js** (2026-08-27), which is SSR-capable and not statically exportable the way the old vanilla frontend was — the original spec's "one container serves API + static frontend" assumption no longer holds.
- **The async artifact-ingestion pipeline** (`infra/terraform/artifact-pipeline/`, 2026-09-02) was built and is the repo's only existing Terraform, but has never been applied — its README already documents an expected composition with "the main app's own deployment work" that was never built. This spec is that missing piece.
- **A 2026-09-09 decision** (recorded in the assistant's memory, confirmed again in this conversation) commits this repo to Terraform-only infrastructure provisioning — no manual console changes, no ad hoc `gcloud` commands left unrecorded.

## Non-Goals

- **Not a production pilot.** This is explicitly a development-scale deployment — see Cost & Scaling Discipline below. Re-evaluate sizing, alerting, and the single-environment assumption before any real pilot traffic.
- **No custom domain.** Both services get their default `*.run.app` HTTPS URL.
- **No OpenAI or Anthropic secrets provisioned.** Only Gemini (via Vertex AI/IAM, no stored key) is wired up as the active LLM provider. The `AnthropicAdapter`/`OpenAIAdapter` code paths remain fully functional and reachable via the admin settings panel — they're just not *provisioned* here. Switching later means adding a Secret Manager secret and an IAM grant, not a code change.
- **No `RESEND_API_KEY`, no `FRONTEND_BASE_URL`.** The Consultant-Initiated Client Invites feature already degrades gracefully to a copy/paste setup link without Resend configured — not worth the extra backend↔frontend deploy-ordering complexity this pass to wire up. `FRONTEND_BASE_URL` falls back to its `http://localhost:3000` default, which only affects the text of that one fallback link.
- **No staging environment.** Single environment, named `dev` (not `cosmos-prod` — deliberately distinct from whatever a future real pilot deployment would be named).
- **No Cloud Monitoring alert policies** (error rate, LLM failures) — deferred, same reasoning as the 2026-08-25 spec: revisit once there's real traffic to monitor. A GCP Billing Budget alert (see below) is a different, much cheaper mechanism that *is* in scope, because it targets the specific concern that prompted this spec revision (cost surprises), not application health.
- **No GCS lifecycle/cleanup policy** for the artifacts bucket. Objects accumulate under `raw/`/`processed/`/`failed/` indefinitely — a known, pre-existing open question (see `documentation/product/roadmap.md`'s Async Artifact Ingestion Pipeline section), not resolved here.

## Architecture

```
                    ┌──────────────────────┐
                    │   Browser (dev use)   │
                    └───────────┬───────────┘
                                │ HTTPS
              ┌─────────────────┴──────────────────┐
              ▼                                      ▼
   ┌─────────────────────────┐          ┌──────────────────────────┐
   │  cosmos-dev-frontend      │  fetch   │  cosmos-dev-backend        │
   │  Cloud Run (Next.js,      │─────────▶│  Cloud Run (FastAPI)       │
   │  next start)              │          │  min=0 max=2, 2Gi/2CPU     │
   │  min=0 max=2, 512Mi/1CPU  │          └──┬──────────┬──────────┬──┘
   └────────────────────────────┘             │          │          │
                                               ▼          ▼          ▼
                                    ┌──────────────┐ ┌─────────┐ ┌─────────────────┐
                                    │ Neon Postgres │ │ Vertex  │ │ GCS: artifacts +  │
                                    │ (existing,    │ │ AI      │ │ transcribe-staging │
                                    │  reused)      │ │ (Gemini)│ │ buckets            │
                                    └───────────────┘ └─────────┘ └──────────┬────────┘
                                                                              │ Eventarc
                                                                              ▼
                                                                   ┌───────────────────────┐
                                                                   │ cosmos-artifact-       │
                                                                   │ processor Cloud Run    │
                                                                   │ min=0 max=2, 2Gi/2CPU  │
                                                                   │ (existing module)      │
                                                                   └────────────────────────┘
```

**Components:**
- **`cosmos-dev-backend`** (Cloud Run) — the FastAPI app, built from a repo-root `Dockerfile` (same shape as the 2026-08-25 spec's, minus the old vanilla `frontend/` copy step, which no longer exists). Public, `--allow-unauthenticated` (app-level auth is JWT-based, not network-level).
- **`cosmos-dev-frontend`** (Cloud Run) — the Next.js app (`frontend-react/`), built from a new `frontend-react/Dockerfile` running `next start` against a `next.config.ts` with `output: "standalone"` added. Public, `--allow-unauthenticated`.
- **`cosmos-artifact-processor`** (Cloud Run, existing module, not yet applied) — unchanged in shape from its 2026-09-02 design; this spec is what finally supplies the two external inputs its README describes (`database_url_secret_id`, `transcribe_bucket_name`) plus a small refactor (below) to source `backend_service_account_email` the same way.
- **Neon Postgres** — the existing local-dev database, reused as-is. No new Neon project/branch.
- **Vertex AI (Gemini)** — reached via `cosmos-backend-sa`'s own IAM identity, no API key stored anywhere.

## Terraform Module Layout

A new module, `infra/terraform/backend/` — sibling to `infra/terraform/artifact-pipeline/`, following the exact same conventions (a `variables.tf`/`main.tf`/`outputs.tf`/`versions.tf`/`README.md` shape, a `cosmos-tfstate-<env>` GCS state bucket created once via the same manual prerequisite step documented in `artifact-pipeline/README.md`).

**`infra/terraform/backend/` provisions:**
- Enables required APIs: `run.googleapis.com`, `artifactregistry.googleapis.com`, `secretmanager.googleapis.com`, `aiplatform.googleapis.com`, `iamcredentials.googleapis.com`, `cloudbuild.googleapis.com` (the last three are also needed once `artifact-pipeline` is composed in).
- Artifact Registry repo: `cosmos` (Docker format).
- Secret Manager secrets: `DATABASE_URL`, `JWT_SECRET_KEY` — both seeded from the values already in the repo's local `.env` (not committed; passed as `-var` or via a local `terraform.tfvars` that's gitignored, same as any Terraform secret input).
- The transcribe-staging GCS bucket (`cosmos-transcribe-<env>` — a new bucket this module owns, distinct from the artifacts bucket `artifact-pipeline` owns).
- Service accounts: `cosmos-backend-sa` (moved here from `artifact-pipeline`, see refactor below), `cosmos-frontend-sa` (minimal — no GCP permissions needed, it only makes outbound HTTPS calls to the backend's public URL), `cosmos-deploy-sa` (GitHub Actions deploy identity) + Workload Identity Federation pool/provider scoped to this repo.
- IAM grants on `cosmos-backend-sa`: `secretmanager.secretAccessor` on its two secrets, `aiplatform.user` for Vertex AI.
- The two Cloud Run services themselves (`cosmos-dev-backend`, `cosmos-dev-frontend`).
- Outputs: `backend_service_account_email`, `database_url_secret_id`, `transcribe_bucket_name`, `backend_url`, `frontend_url` — the first three are exactly what `artifact-pipeline`'s existing variables expect.

**Refactor to the existing `infra/terraform/artifact-pipeline/` module:** it currently creates `google_service_account "backend"` (`cosmos-backend-sa`) itself. That identity belongs with the backend's own deployment, not a downstream pipeline module that only needs to grant it extra permissions — so this spec moves that resource into `infra/terraform/backend/` and changes `artifact-pipeline/variables.tf` to accept `backend_service_account_email` as an input (same pattern already used for `database_url_secret_id`/`transcribe_bucket_name`), updating the handful of `google_service_account.backend.email` references in `main.tf` to `var.backend_service_account_email`. Everything else in that module (the artifacts bucket, Eventarc trigger, processor service, `cosmos-processor-sa`) is untouched in shape — only the min/max-instance scaling addition below and this one variable threading change.

**Apply order:** `infra/terraform/backend/` first (its outputs feed the second module) → `infra/terraform/artifact-pipeline/` second, exactly as that module's own README already documents.

## Cost & Scaling Discipline

Prompted directly by a prior incident (an Eventarc self-retrigger loop that repeatedly reprocessed the same file) and the fact that this is unfunded, personal-account work. Two things are true here: **the specific bug that caused that incident is already fixed in the code that exists today** (`backend/processor_main.py:67-73` returns `200 skipped` for the processor's own `processed/`/`failed/` writes instead of raising, which is what stops Eventarc from retrying; a status-based idempotency guard at line 84 covers genuine re-deliveries too; every code path in that file returns `200`, never a `5xx` Eventarc would retry). This spec adds defense-in-depth on top of that fix, not a replacement for it:

- **Explicit `min_instance_count = 0` on all three Cloud Run services** — `cosmos-dev-backend`, `cosmos-dev-frontend`, and `cosmos-artifact-processor` (which currently has no scaling block at all, relying on an unstated Cloud Run default). True scale-to-zero on every service; cold starts are an accepted dev-scale tradeoff.
- **Explicit `max_instance_count = 2` on all three** — including the processor, which currently has no cap and would otherwise inherit Cloud Run's default ceiling of 100. Even a genuine event storm can't scale wide.
- **No "always allocate CPU"** on any service — default Cloud Run billing (CPU allocated only during active request handling), not the always-on CPU mode.
- **A GCP Billing Budget**, $5/month threshold, with an email alert — provisioned via Terraform (`google_billing_budget`) in the `backend` module, tied to the `cosmos-strategy` project's existing billing account.

## Secrets & IAM Summary

| Secret/Identity | Holds / Grants | Source |
|---|---|---|
| `DATABASE_URL` (Secret Manager) | Neon connection string | Copied from local `.env`, reused as-is (same database) |
| `JWT_SECRET_KEY` (Secret Manager) | JWT signing key | Copied from local `.env`, reused as-is |
| `cosmos-backend-sa` | `secretmanager.secretAccessor` (its 2 secrets), `aiplatform.user`, plus GCS grants from `artifact-pipeline` | New (moved from `artifact-pipeline`, see refactor above) |
| `cosmos-frontend-sa` | Nothing beyond default Cloud Run runtime permissions | New |
| `cosmos-deploy-sa` | `run.developer`, `artifactregistry.writer`, `iam.serviceAccountUser` on `cosmos-backend-sa`/`cosmos-frontend-sa`, bound to GitHub's OIDC via WIF | New |
| `cosmos-processor-sa` | Unchanged from the existing module | Existing, unapplied |

No `ADMIN_API_TOKEN`. No `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`. `GCP_PROJECT_ID=cosmos-strategy` and `GCP_LOCATION=us-central1` are plain (non-secret) env vars on the backend service, for the `GeminiAdapter`.

## CI/CD

`.github/workflows/ci.yml` (tests, already exists) is untouched. New `.github/workflows/deploy.yml`, triggered on push to `main`, gated by a GitHub `dev` environment's manual-approval rule (renamed from the old spec's `production`, matching this deployment's actual scope):

1. Build + push the backend image to Artifact Registry.
2. Run `backend/database.py` (idempotent schema migration/seed), then one additional idempotent statement: `UPDATE platform_settings SET active_llm_provider = 'gemini' WHERE id = 1;` — so a fresh deploy comes up already on Gemini, not requiring a manual admin-panel switch afterward.
3. Deploy `cosmos-dev-backend`; capture its URL.
4. Build + push the frontend image, with that URL baked in as `NEXT_PUBLIC_API_BASE` (a Next.js public env var — inlined at build time, which is why backend must deploy first).
5. Deploy `cosmos-dev-frontend`.

Auth via Workload Identity Federation (no downloaded service-account JSON keys), same as the 2026-08-25 spec's design.

## Open Items / Dependencies

- The one-time Terraform state bucket (`cosmos-tfstate-dev`) needs creating before first `terraform init`, per `artifact-pipeline/README.md`'s existing documented prerequisite — same step, same pattern, just also needed for the new `backend` module's state.
- `GITHUB_REPO` for the WIF provider's attribute condition is `balajir2/Cosmos-Strategy-Platform` (confirmed from the repo's own git remote).
- The GitHub `dev` environment's manual-approval rule and branch-protection "required check" settings are manual GitHub UI steps (same as the original spec) — not something Terraform or this repo's code can configure.
- `backend_url`/`frontend_url` outputs exist on the `backend` module for convenience, but the real ordering dependency (frontend's Docker build needing the backend's already-deployed URL) is resolved by the CI workflow's step order (§ CI/CD above), not by Terraform alone — Terraform doesn't build container images.
- The `google_billing_budget` resource requires the authenticated identity to hold a billing-account-level role (e.g. Billing Account Costs Manager), not just project-level Owner/Editor — this is separate from every other permission this spec needs, which are all project-scoped. If `terraform apply` fails on that resource specifically for a permissions reason, the fallback is creating the $5 budget once by hand in the Billing console (a one-time exception to "Terraform only," scoped narrowly to this single resource, documented if it happens).
