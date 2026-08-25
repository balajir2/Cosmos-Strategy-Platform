# Design Spec: Production Deployment Architecture — GCP Cloud Run

**Date:** 2026-08-25
**Status:** Approved for planning

## Goal

Define the target-state production deployment architecture for the Cosmos Strategic Capability Platform, to be implemented once Phases A (Auth), B (Projects), and C (Engagement Knowledge Base) from `documentation/product/roadmap.md` are built. This is not something deployed today — the current codebase is still POC-stage (hardcoded Blazar/Basil cases, no auth). This spec is written now so the deployment target is known while those phases are being built, avoiding architecture decisions made under deploy-day time pressure.

Scope is a **small enterprise pilot**: a handful of concurrent consulting engagements, tens of concurrent users, single region, no committed multi-region SLA. "Enterprise-grade" here means solid security/observability/operational practices at this scale, not hyperscale infrastructure — the design explicitly avoids overbuilding for scale or compliance requirements that don't exist yet (see Non-Goals).

## Decision Rationale

- **Cloud platform: GCP, not AWS.** The current codebase uses AWS Bedrock for the LLM, which would be the natural reason to standardize on AWS. This spec pairs the GCP decision with dropping Bedrock as a hard dependency (see next point) — once that's gone, nothing in the stack requires AWS. GCP Cloud Run's billing model (true scale-to-zero, no load-balancer minimum charge) is a better fit for a pilot with sporadic, workshop-driven traffic than AWS's ECS Fargate + ALB (fixed hourly cost even at idle) or its well-known variable costs (NAT Gateway, cross-AZ transfer). Neon Postgres is unaffected by this choice — it's a separate managed service, already cloud-agnostic.
- **LLM: pluggable multi-provider (Anthropic, OpenAI, Gemini), admin-switchable at runtime — not a fixed Bedrock dependency.** Requirement: the platform owner needs to choose the AI provider without a code deploy, and already holds accounts across AWS, GCP, and (implicitly) OpenAI/Anthropic. `backend/rag_engine.py`'s `boto3` Bedrock client is replaced with a small provider abstraction (see LLM Provider Abstraction below) so no single vendor is hardwired into the evaluation pipeline. This is an isolated, well-bounded change — the RAG retrieval logic (embedding + pgvector search) is untouched; only the "call the LLM and parse its response" step becomes provider-agnostic.
- **Compute: Cloud Run, not GKE or a Compute Engine VM.** Considered three options:
  - **Cloud Run (chosen)**: serverless containers, scale-to-zero, automatic HTTPS/TLS, zero-downtime rolling deploys, no servers to patch. Matches a solo/small-team pilot.
  - **GKE Autopilot**: more control and better fit if the roadmap's four future product modules become genuinely separate services later, but meaningfully more operational surface (cluster upgrades, networking config) than a single-service pilot justifies today. Revisit if/when that happens.
  - **Compute Engine VM + Docker Compose**: cheapest floor, but you own patching, scaling, TLS, and zero-downtime deploys yourself — doesn't earn the "enterprise-grade" label without reinventing what Cloud Run gives for free.
- **Single environment (`cosmos-prod`), not staging + prod.** Simplifies the architecture at pilot scale; the safety net is Cloud Run's revision-based rollback (instant, no rebuild) plus a manual approve-to-deploy gate in CI, rather than a separate staging environment.
- **No specific compliance framework targeted.** No client currently requires SOC2/HIPAA/etc. The design uses solid default security practice (Secret Manager, least-privilege IAM, Workload Identity Federation) and explicitly defers compliance-driven additions (VPC Service Controls, customer-managed encryption keys, audit-log export pipelines) until an actual requirement exists.

## Non-Goals

- Multi-region or high-availability failover — no committed enterprise SLA exists yet.
- SOC2 / HIPAA / other compliance certification — revisit if a client requires one.
- Multi-firm tenant isolation (isolating separate consulting firms on one deployment) — out of scope per the roadmap's "Beyond the POC" section; only per-project isolation (already addressed by Phase B/C's `project_id` scoping) is in scope here.
- Kubernetes/GKE — deferred until multiple genuinely separate services exist.
- Redesigning authentication or the RAG pipeline itself — this spec only defines where Phase A's JWT secret lives and how the LLM call becomes provider-agnostic; the auth and retrieval logic are specified elsewhere (Users/Projects/Engagement KB spec).
- Per-project provider selection — the provider switch is a single platform-wide setting, not a per-engagement choice. Revisit only if a real need for per-project provider choice emerges.

## Architecture

```
                         ┌─────────────────────┐
                         │   Users (browser)    │
                         └──────────┬───────────┘
                                    │ HTTPS
                         ┌──────────▼───────────┐
                         │  Cloud Run service    │
                         │  (FastAPI + static    │
                         │   frontend, 1 image)  │
                         │  autoscale 0→N        │
                         └──┬────────┬───────┬───┘
                            │        │       │
              ┌─────────────┘        │       └───────────────┐
              ▼                      ▼                       ▼
   ┌─────────────────────┐  ┌────────────────┐   ┌─────────────────────┐
   │   Neon Postgres      │  │ LLM Provider    │   │  GCP Secret Manager  │
   │  (+ pgvector,        │  │ Abstraction     │   │  (DATABASE_URL,      │
   │   existing service;  │  │ (reads active   │   │   ANTHROPIC_API_KEY, │
   │   also holds the     │  │  provider from  │   │   OPENAI_API_KEY,    │
   │   platform_settings  │  │  platform_      │   │   JWT signing key)   │
   │   table)             │  │  settings row)  │   └─────────────────────┘
   └──────────────────────┘  └───┬────┬────┬───┘
                                  │    │    │
                    ┌─────────────┘    │    └─────────────┐
                    ▼                  ▼                  ▼
         ┌──────────────────┐ ┌────────────────┐ ┌─────────────────────┐
         │  Anthropic API    │ │  OpenAI API     │ │  Vertex AI (Gemini)  │
         │  (direct)         │ │  (direct)       │ │  (GCP IAM, no key)   │
         └───────────────────┘ └─────────────────┘ └───────────────────────┘
```

**Components:**
- **Cloud Run service (`cosmos-prod`)** — the only compute component. One container image holds the FastAPI app; it serves both the API routes and the static frontend files directly, matching how `main.py` already works today — no separate static hosting tier. A custom domain is mapped via Cloud Run domain mapping (a GCP HTTPS Load Balancer + Cloud CDN in front is a later addition, not needed at this scale).
- **Neon Postgres** — unchanged from Phase 0, plus one new table: `platform_settings` (single row, holds `active_llm_provider`; see LLM Provider Abstraction below). Reached over the public internet via TLS using the pooled connection string Neon already provides; no VPC peering required.
- **LLM Provider Abstraction** — a new `backend/llm_provider.py` module in the FastAPI app (not a separate deployed service) that reads the active provider from `platform_settings` and routes the evaluate call to the corresponding adapter. Detailed below.
- **GCP Secret Manager** — holds `DATABASE_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and the JWT signing secret (once Phase A ships). No Gemini key is stored — Gemini is reached via Vertex AI using the Cloud Run service's own IAM identity (see below). Mounted as env vars into the Cloud Run service at deploy time. Nothing sensitive lives in the repo or in plain Cloud Run env config.

## LLM Provider Abstraction

**Requirement**: the platform owner can switch between Anthropic, OpenAI, and Gemini as the active LLM provider without a code deploy.

- **Setting storage**: a single-row `platform_settings` table in Neon Postgres (`active_llm_provider TEXT NOT NULL DEFAULT 'anthropic' CHECK (active_llm_provider IN ('anthropic','openai','gemini'))`, `updated_at`, `updated_by` referencing `users(id)`). A row, not a generic key-value table — there's exactly one setting today, and a KV table would be speculative generality for a value that doesn't exist yet.
- **Admin control**: `GET /api/admin/settings` and `PATCH /api/admin/settings` (SystemAdmin-only, per Phase A's `require_admin` dependency) to read/change the active provider. A small settings panel in the frontend (a dropdown, not previously in the roadmap's frontend checklist — flagged as new scope) calls this endpoint.
- **Read path**: `rag_engine.py`'s evaluate flow reads `platform_settings` on each request. At pilot-scale request volume this DB read is cheap enough that no caching layer is needed initially; add a short in-process cache only if it shows up as a real cost/latency issue later.
- **Provider adapters**: a common interface (e.g. `generate_evaluation(prompt, context) -> EvaluationResult`) with three implementations:
  - `AnthropicAdapter` — direct Anthropic API via the `anthropic` SDK. Default/current model: Claude Sonnet 5.
  - `OpenAIAdapter` — direct OpenAI API via the `openai` SDK, API key from Secret Manager.
  - `GeminiAdapter` — **Vertex AI**, not the direct Gemini API key. Uses the Cloud Run service's existing GCP service account (Application Default Credentials) — no separate API key to provision, store, or rotate, consistent with this spec's preference for IAM-based access over floating API keys wherever GCP makes that available.
  - Each adapter normalizes its provider's response into the same shape the rest of the pipeline already expects (today: `rating`/`critique`/`recommendations`; later: the Level 1/2/3 comparative benchmark shape from the Guided Learning Flow design) — call-site code in `rag_engine.py` doesn't need to know which provider answered.
- **Failure behavior**: the existing graceful-degradation fallback (local heuristic critique when the LLM is unavailable) applies uniformly regardless of which provider is active — a provider-specific outage degrades the same way an AWS Bedrock outage does today.
- **Scope note**: this is a genuinely new piece of implementation work — it doesn't exist in any form today (the current code has exactly one hardcoded Bedrock client) — sized as its own task in the eventual implementation plan, not a one-line config change.

## CI/CD

Single environment, GitHub Actions:

1. **Any push/PR** → run `pytest` + lint. Blocks merge on failure.
2. **Merge to `main`** → build the Docker image → push to Artifact Registry → run DB migrations (`database.py` DDL, only when schema changed) → **manual approve-to-deploy step** → deploy new revision to `cosmos-prod`.

The manual approval step (a one-click approval in GitHub Actions, not a separate staging environment) exists because there's no staging gate to catch a bad merge before it reaches the only environment that exists. Rollback is re-pointing Cloud Run traffic to the previous revision — instant, no rebuild required, since Cloud Run retains prior revisions by default.

## Security & Identity

- **Secrets**: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`, and the JWT signing secret live in GCP Secret Manager — never committed to the repo, never in plain `.env` files in production. Gemini access via Vertex AI needs no stored API key (see LLM Provider Abstraction).
- **CI authentication**: GitHub Actions authenticates to GCP via **Workload Identity Federation** (short-lived tokens tied to the GitHub repo), not a downloaded long-lived service-account JSON key.
- **Transport**: Cloud Run terminates HTTPS automatically with a managed TLS certificate on the custom domain. Neon connections are TLS by default.
- **IAM**: a dedicated GCP service account for the Cloud Run service, scoped to reading its own secrets plus the `roles/aiplatform.user` role for Vertex AI (Gemini) access — not a broad project-editor role. A separate, narrowly-scoped identity for the GitHub Actions deploy path (deploy + Artifact Registry push only).
- **Application-level auth** (JWT login, `require_admin`/`require_project_role` dependencies) is Phase A/B's responsibility per the roadmap — this spec only provisions the secret slot for it.

## Observability & Operations

- **Logging**: Cloud Run auto-captures stdout/stderr into Cloud Logging. App logs should be structured as JSON (a small change to `main.py`/`rag_engine.py`'s logging) so entries are filterable by fields like `project_id` or `request_id`.
- **Metrics & alerting**: Cloud Run auto-reports request count, latency, error rate, and instance count to Cloud Monitoring at no extra cost. Two alerting policies at minimum: error rate above threshold (e.g. >5% 5xx over 5 minutes), and Anthropic API failures/timeouts (a custom log-based metric) — the latter matters because the existing graceful-degradation fallback (local heuristic critique when the LLM is unavailable) could otherwise mask a real outage silently.
- **Health checks**: a lightweight `/healthz` route (add if `main.py` doesn't already have one) so a bad deploy fails fast before receiving traffic.
- **Backup/DR**: Neon's built-in point-in-time restore covers the database; no separate backup job needed. The restore procedure (retention window on the current plan) should be documented once, not discovered for the first time during an incident.
- **Incident runbook**: bad revision → Cloud Run rollback to the previous revision (one command/click); bad data → Neon point-in-time restore.

## Cost Estimate (approximate, small pilot scale)

| Component | Estimate | Basis |
|---|---|---|
| Cloud Run | $0–10/mo | Free tier (2M requests + 360K vCPU-seconds/month) likely covers pilot volume with scale-to-zero |
| Secret Manager | <$1/mo | ~$0.06/secret-version/month × 4 secrets |
| Artifact Registry | <$1/mo | Docker image storage, a few hundred MB |
| Cloud Logging/Monitoring | $0/mo | Free tier (50GB logs/mo) exceeds pilot volume |
| Neon Postgres | $0–19/mo | Free tier may suffice early; entry paid tier (~$19/mo) if outgrown |
| LLM API (active provider) | ~$5–50/mo | At ~500–2,000 evaluate calls/month, ~2K input + ~800 output tokens each — this figure is for Anthropic Sonnet 5 as the default; switching the active provider changes this line (see note below) |
| Domain/DNS | ~$1/mo | If not already owned |
| GitHub Actions | $0/mo | Free-tier minutes cover solo/small-team scale |
| **Total** | **~$10–80/month** | Dominated by Neon's tier and actual LLM usage volume, not infra |

Anthropic pricing verified live against current rates as of this spec's date (Sonnet 5: $2/$10 per million input/output tokens through an intro period ending 2026-08-31, then $3/$15). GCP/Neon figures are general knowledge of published pricing tiers, not a live lookup. **OpenAI and Gemini per-token pricing were not looked up for this spec** — since the provider is admin-switchable, get current pricing for whichever provider is actually active before relying on this estimate; the shape of the cost (dominated by call volume × per-token rate) is the same across all three.

## Scaling Posture

Deliberately simple, with clear single-lever upgrades:
- **More traffic** → raise Cloud Run's max-instances setting; no architecture change.
- **More DB load** → increase Neon's compute size or add a read replica; no app-level change.
- **Multiple product modules become real separate services** (per the roadmap's "Beyond the POC" section) → revisit GKE Autopilot at that point, not before.
- **A client requires SOC2/HIPAA/data residency** → add VPC Service Controls, audit-log export, customer-managed encryption keys at that point, not before.

## Open Items / Dependencies

- Depends on Phases A (Auth), B (Projects), and C (Engagement KB) shipping first — this spec provisions the JWT secret slot and the `platform_settings` table but does not design auth itself. The admin settings endpoint depends on Phase A's `require_admin` dependency existing.
- The LLM Provider Abstraction (`backend/llm_provider.py`, `platform_settings` table, admin settings endpoint + frontend panel) is new implementation scope not previously listed anywhere in the roadmap — needs its own line item when this spec moves to an implementation plan.
- OpenAI and Gemini accounts/API access need to actually be provisioned (Gemini via Vertex AI enablement on the GCP project) before those adapters can be built or tested.
- Domain name and DNS provider not yet decided — needed before Cloud Run domain mapping can be configured.
