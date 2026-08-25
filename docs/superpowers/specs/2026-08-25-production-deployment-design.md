# Design Spec: Production Deployment Architecture — GCP Cloud Run

**Date:** 2026-08-25
**Status:** Approved for planning

## Goal

Define the target-state production deployment architecture for the Cosmos Strategic Capability Platform, to be implemented once Phases A (Auth), B (Projects), and C (Engagement Knowledge Base) from `documentation/product/roadmap.md` are built. This is not something deployed today — the current codebase is still POC-stage (hardcoded Blazar/Basil cases, no auth). This spec is written now so the deployment target is known while those phases are being built, avoiding architecture decisions made under deploy-day time pressure.

Scope is a **small enterprise pilot**: a handful of concurrent consulting engagements, tens of concurrent users, single region, no committed multi-region SLA. "Enterprise-grade" here means solid security/observability/operational practices at this scale, not hyperscale infrastructure — the design explicitly avoids overbuilding for scale or compliance requirements that don't exist yet (see Non-Goals).

## Decision Rationale

- **Cloud platform: GCP, not AWS.** The current codebase uses AWS Bedrock for the LLM, which would be the natural reason to standardize on AWS. This spec pairs the GCP decision with dropping Bedrock (see next point) — once that dependency is gone, nothing in the stack requires AWS. GCP Cloud Run's billing model (true scale-to-zero, no load-balancer minimum charge) is a better fit for a pilot with sporadic, workshop-driven traffic than AWS's ECS Fargate + ALB (fixed hourly cost even at idle) or its well-known variable costs (NAT Gateway, cross-AZ transfer). Neon Postgres is unaffected by this choice — it's a separate managed service, already cloud-agnostic.
- **LLM: direct Anthropic API, not AWS Bedrock.** Keeping Bedrock while hosting on GCP would mean every LLM call crosses clouds (GCP compute → AWS IAM/SigV4 auth → Bedrock), adding latency, a second cloud's IAM surface to secure, and cross-cloud egress cost that partly erases GCP's savings. The direct Anthropic API needs only a bearer-token SDK client, no AWS account or IAM roles. `backend/rag_engine.py`'s `boto3` Bedrock client is replaced with the `anthropic` Python SDK — an isolated change, not a redesign of the RAG pipeline itself.
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
- Redesigning authentication or the RAG pipeline itself — this spec only defines where Phase A's JWT secret lives and how Bedrock is swapped for the direct API; the auth and retrieval logic are specified elsewhere (Users/Projects/Engagement KB spec).

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
                         └──────┬───────┬────────┘
                                │       │
                 ┌──────────────┘       └───────────────┐
                 ▼                                       ▼
      ┌─────────────────────┐               ┌───────────────────────┐
      │   Neon Postgres      │               │  Anthropic API         │
      │  (+ pgvector,        │               │  (direct, not Bedrock) │
      │   existing service)  │               └───────────────────────┘
      └──────────────────────┘
                 ▲
                 │ secrets injected at runtime
      ┌──────────┴───────────┐
      │  GCP Secret Manager   │
      │  (DATABASE_URL,       │
      │   ANTHROPIC_API_KEY,  │
      │   JWT signing key)    │
      └────────────────────────┘
```

**Components:**
- **Cloud Run service (`cosmos-prod`)** — the only compute component. One container image holds the FastAPI app; it serves both the API routes and the static frontend files directly, matching how `main.py` already works today — no separate static hosting tier. A custom domain is mapped via Cloud Run domain mapping (a GCP HTTPS Load Balancer + Cloud CDN in front is a later addition, not needed at this scale).
- **Neon Postgres** — unchanged from Phase 0. Reached over the public internet via TLS using the pooled connection string Neon already provides; no VPC peering required.
- **Anthropic API** — replaces Bedrock in `rag_engine.py`. Model: Claude Sonnet 5 (cost-appropriate for a single-answer evaluation call; upgradeable to Opus 5 if evaluation quality needs it).
- **GCP Secret Manager** — holds `DATABASE_URL`, `ANTHROPIC_API_KEY`, and the JWT signing secret (once Phase A ships). Mounted as env vars into the Cloud Run service at deploy time. Nothing sensitive lives in the repo or in plain Cloud Run env config.

## CI/CD

Single environment, GitHub Actions:

1. **Any push/PR** → run `pytest` + lint. Blocks merge on failure.
2. **Merge to `main`** → build the Docker image → push to Artifact Registry → run DB migrations (`database.py` DDL, only when schema changed) → **manual approve-to-deploy step** → deploy new revision to `cosmos-prod`.

The manual approval step (a one-click approval in GitHub Actions, not a separate staging environment) exists because there's no staging gate to catch a bad merge before it reaches the only environment that exists. Rollback is re-pointing Cloud Run traffic to the previous revision — instant, no rebuild required, since Cloud Run retains prior revisions by default.

## Security & Identity

- **Secrets**: `ANTHROPIC_API_KEY`, `DATABASE_URL`, and the JWT signing secret live in GCP Secret Manager — never committed to the repo, never in plain `.env` files in production.
- **CI authentication**: GitHub Actions authenticates to GCP via **Workload Identity Federation** (short-lived tokens tied to the GitHub repo), not a downloaded long-lived service-account JSON key.
- **Transport**: Cloud Run terminates HTTPS automatically with a managed TLS certificate on the custom domain. Neon connections are TLS by default.
- **IAM**: a dedicated GCP service account for the Cloud Run service, scoped only to reading its own secrets — not a broad project-editor role. A separate, narrowly-scoped identity for the GitHub Actions deploy path (deploy + Artifact Registry push only).
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
| Secret Manager | <$1/mo | ~$0.06/secret-version/month × 3 secrets |
| Artifact Registry | <$1/mo | Docker image storage, a few hundred MB |
| Cloud Logging/Monitoring | $0/mo | Free tier (50GB logs/mo) exceeds pilot volume |
| Neon Postgres | $0–19/mo | Free tier may suffice early; entry paid tier (~$19/mo) if outgrown |
| Anthropic API (Sonnet 5) | ~$5–50/mo | At ~500–2,000 evaluate calls/month, ~2K input + ~800 output tokens each |
| Domain/DNS | ~$1/mo | If not already owned |
| GitHub Actions | $0/mo | Free-tier minutes cover solo/small-team scale |
| **Total** | **~$10–80/month** | Dominated by Neon's tier and actual Anthropic usage volume, not infra |

Anthropic pricing verified live against current rates as of this spec's date (Sonnet 5: $2/$10 per million input/output tokens through an intro period ending 2026-08-31, then $3/$15). GCP/Neon figures are general knowledge of published pricing tiers, not a live lookup — worth confirming against each provider's calculator once expected engagement volume is known.

## Scaling Posture

Deliberately simple, with clear single-lever upgrades:
- **More traffic** → raise Cloud Run's max-instances setting; no architecture change.
- **More DB load** → increase Neon's compute size or add a read replica; no app-level change.
- **Multiple product modules become real separate services** (per the roadmap's "Beyond the POC" section) → revisit GKE Autopilot at that point, not before.
- **A client requires SOC2/HIPAA/data residency** → add VPC Service Controls, audit-log export, customer-managed encryption keys at that point, not before.

## Open Items / Dependencies

- Depends on Phases A (Auth), B (Projects), and C (Engagement KB) shipping first — this spec provisions the JWT secret slot but does not design auth itself.
- `rag_engine.py`'s Bedrock → direct Anthropic API swap is a small, isolated implementation task, not yet scheduled into a roadmap phase.
- Domain name and DNS provider not yet decided — needed before Cloud Run domain mapping can be configured.
