# GCP Production Deployment Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the GCP infrastructure and CI/CD pipeline to run the Cosmos backend on Cloud Run as `cosmos-prod`, per the approved deployment spec.

**Architecture:** One Cloud Run service built from a single Docker image (FastAPI + static frontend). GitHub Actions runs tests on every push/PR, and on merge to `main` builds the image, runs DB migrations, and deploys to Cloud Run after a manual approval gate (a GitHub Environment protection rule, not a separate staging environment). Secrets live in GCP Secret Manager; GitHub Actions authenticates via Workload Identity Federation (no downloaded service-account keys).

**Tech Stack:** Docker, GCP (Cloud Run, Artifact Registry, Secret Manager, IAM, Cloud Monitoring), GitHub Actions, `google-github-actions/auth` + `setup-gcloud`.

**Spec:** `docs/superpowers/specs/2026-08-25-production-deployment-design.md`

**Depends on:** `docs/superpowers/plans/2026-08-25-llm-provider-abstraction.md` being implemented first — this plan's Cloud Run deploy step wires up the `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ADMIN_API_TOKEN`, `GCP_PROJECT_ID`, and `GCP_LOCATION` env vars/secrets that plan introduces.

## Global Constraints

- Single environment: `cosmos-prod`. No staging environment.
- Deploys to `cosmos-prod` require manual approval — never fully automatic on merge to `main`.
- Rollback is Cloud Run's built-in revision traffic-shifting — no separate rollback tooling.
- GitHub Actions authenticates to GCP via Workload Identity Federation — no long-lived service-account JSON keys committed or stored as GitHub secrets.
- The Cloud Run service account is scoped to only: reading its own Secret Manager secrets, and `roles/aiplatform.user` for Vertex AI (Gemini) access. Never a broad `roles/editor`.
- Replace `<PROJECT_ID>`, `<REGION>`, `<GITHUB_ORG>/<GITHUB_REPO>` placeholders below with real values once — they're environment-specific, not left incomplete.

---

### Task 1: Health check endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_healthz.py`

**Interfaces:**
- Produces: `GET /healthz` — used by Cloud Run's startup/liveness probing (Task 6's deploy config assumes this route exists).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_healthz.py
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)


def test_healthz_returns_ok():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_healthz.py -v`
Expected: FAIL with 404 (route doesn't exist)

- [ ] **Step 3: Add the route to `backend/main.py`**

Add near the top of the routes, before `/api/status`:
```python
@app.get("/healthz")
def healthz():
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_healthz.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_healthz.py
git commit -m "feat: add /healthz endpoint for Cloud Run health checks"
```

---

### Task 2: Dockerfile

**Files:**
- Create: `Dockerfile` (repo root)
- Create: `.dockerignore` (repo root)

**Interfaces:** none (build artifact only)

- [ ] **Step 1: Write `.dockerignore`**

```
.git
.env
.venv
venv/
__pycache__/
*.pyc
tests/
docs/
documentation/
*.md
README.pdf
```

Note: `archives/` (the source PDFs) is deliberately **included** in the build context here, not excluded — `rag_engine.py`'s `load_or_build_index()` only re-ingests them if `framework_kb_chunks` is empty, which won't be true against the shared production Neon database (already seeded per Phase 0), but leaving them out would silently break a fresh/empty database. If image size becomes a concern later, revisit once Phase 0's seeding is confirmed to always run before first deploy.

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY archives/ archives/

ENV PORT=8080
EXPOSE 8080

CMD uvicorn main:app --app-dir /app/backend --host 0.0.0.0 --port ${PORT}
```

`--app-dir /app/backend` puts `backend/` on the import path so `main:app` resolves, without running `main.py`'s own `if __name__ == "__main__":` block (which sets `reload=True` — a dev-only setting that has no place in a production container).

- [ ] **Step 3: Build and run locally to verify**

Run (from repo root, with a real or test `DATABASE_URL`, `ANTHROPIC_API_KEY` available):
```bash
docker build -t cosmos-app:local .
docker run --rm -p 8080:8080 --env-file .env cosmos-app:local
```

Expected: container starts, logs show `Initializing RAG Engine...` then Uvicorn's "Application startup complete", and `curl http://localhost:8080/healthz` returns `{"status":"ok"}`.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "build: add Dockerfile for Cloud Run deployment"
```

---

### Task 3: GCP project bootstrap (APIs, Artifact Registry, service accounts)

**Files:** none (infrastructure, not repo code) — record the exact commands run in this task's PR description or a one-time setup note, since they aren't re-run by CI.

**Interfaces:**
- Produces: an Artifact Registry repo, two IAM service accounts (`cosmos-run-sa`, `cosmos-deploy-sa`) — consumed by Task 4 (WIF binding) and Task 6 (deploy workflow).

Set these once at the top of your shell for the rest of this task and Task 4:
```bash
export PROJECT_ID=<PROJECT_ID>
export REGION=<REGION>          # e.g. us-central1
export REPO_NAME=cosmos
```

- [ ] **Step 1: Enable required APIs**

```bash
gcloud config set project "$PROJECT_ID"

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  iamcredentials.googleapis.com \
  cloudbuild.googleapis.com
```

Expected: each service prints "Operation finished successfully" (or is already enabled).

- [ ] **Step 2: Create the Artifact Registry repo**

```bash
gcloud artifacts repositories create "$REPO_NAME" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Cosmos Strategic Capability Platform container images"
```

Expected: `Created repository [cosmos].`

- [ ] **Step 3: Create the Cloud Run runtime service account**

```bash
gcloud iam service-accounts create cosmos-run-sa \
  --display-name="Cosmos Cloud Run runtime"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:cosmos-run-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:cosmos-run-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

Expected: each binding prints the updated policy including the new member/role pair. This account gets `aiplatform.user` (for the Gemini/Vertex adapter) and `secretmanager.secretAccessor` — nothing broader.

- [ ] **Step 4: Create the GitHub Actions deploy service account**

```bash
gcloud iam service-accounts create cosmos-deploy-sa \
  --display-name="Cosmos GitHub Actions deploy"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:cosmos-deploy-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.developer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:cosmos-deploy-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud iam service-accounts add-iam-policy-binding \
  "cosmos-run-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --member="serviceAccount:cosmos-deploy-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

Expected: bindings confirmed as in Step 3. The last command lets the deploy account tell Cloud Run to run as `cosmos-run-sa` without granting the deploy account the runtime account's own permissions.

---

### Task 4: Secret Manager secrets + Workload Identity Federation

**Files:** none (infrastructure)

**Interfaces:**
- Produces: Secret Manager secrets `DATABASE_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ADMIN_API_TOKEN`; a Workload Identity Pool + Provider bound to `cosmos-deploy-sa` — consumed by Task 6's GitHub Actions workflow via repo secrets `GCP_WIF_PROVIDER` and `GCP_DEPLOY_SA_EMAIL`.

- [ ] **Step 1: Create the secrets**

```bash
printf '%s' "<your Neon connection string>" | gcloud secrets create DATABASE_URL --data-file=-
printf '%s' "<your Anthropic API key>" | gcloud secrets create ANTHROPIC_API_KEY --data-file=-
printf '%s' "<your OpenAI API key>" | gcloud secrets create OPENAI_API_KEY --data-file=-
printf '%s' "$(openssl rand -hex 32)" | gcloud secrets create ADMIN_API_TOKEN --data-file=-
```

Expected: each prints `Created secret [<name>].`. Save the generated `ADMIN_API_TOKEN` value somewhere safe — it's what an admin sends as the `x-admin-token` header to `/api/admin/settings`.

- [ ] **Step 2: Grant the runtime service account access to each secret**

```bash
for secret in DATABASE_URL ANTHROPIC_API_KEY OPENAI_API_KEY ADMIN_API_TOKEN; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:cosmos-run-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

Expected: four confirmations, one per secret.

- [ ] **Step 3: Create the Workload Identity Pool and Provider**

```bash
export GITHUB_REPO=<GITHUB_ORG>/<GITHUB_REPO>

gcloud iam workload-identity-pools create "github-pool" \
  --location="global" \
  --display-name="GitHub Actions pool"

gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub OIDC provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"
```

Expected: pool and provider each print a "Created" confirmation. The `attribute-condition` restricts the provider to only this repo's tokens.

- [ ] **Step 4: Bind the provider to the deploy service account**

```bash
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

gcloud iam service-accounts add-iam-policy-binding \
  "cosmos-deploy-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${GITHUB_REPO}"
```

Expected: confirmation of the updated IAM policy.

- [ ] **Step 5: Record the two values GitHub Actions needs**

```bash
echo "GCP_WIF_PROVIDER=projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
echo "GCP_DEPLOY_SA_EMAIL=cosmos-deploy-sa@${PROJECT_ID}.iam.gserviceaccount.com"
```

Add both, plus `GCP_PROJECT_ID`, `GCP_REGION`, and `GCP_RUNTIME_SA_EMAIL` (`cosmos-run-sa@${PROJECT_ID}.iam.gserviceaccount.com`), as **GitHub repo secrets** (Settings → Secrets and variables → Actions) — no downloaded JSON key is ever created or stored.

---

### Task 5: GitHub Actions — test workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `tests/` (from the LLM Provider Abstraction plan), `backend/requirements.txt`
- Produces: a required status check gating merges to `main`.

- [ ] **Step 1: Write the workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
          pip install pytest

      - name: Run tests
        run: pytest tests/ -v
```

- [ ] **Step 2: Push and verify**

Push this file on a branch and open a PR. Expected: the "CI / test" check appears on the PR and passes (or fails honestly if a real test fails — either way confirms the workflow runs).

- [ ] **Step 3: Make it a required check**

In GitHub repo Settings → Branches → branch protection rule for `main`, add "CI / test" as a required status check.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add test workflow"
```

---

### Task 6: GitHub Actions — build, migrate, and deploy workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: repo secrets from Task 4 (`GCP_WIF_PROVIDER`, `GCP_DEPLOY_SA_EMAIL`, `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_RUNTIME_SA_EMAIL`), the Dockerfile (Task 2), `backend/database.py`'s `init_db()` (existing)
- Produces: a deployed `cosmos-prod` Cloud Run revision on each approved merge to `main`.

- [ ] **Step 1: Create the GitHub Environment protection rule**

In repo Settings → Environments, create an environment named `production`, and add at least one required reviewer under "Deployment protection rules". This is what makes the deploy job below pause for manual approval — no code enforces this, the environment binding does.

- [ ] **Step 2: Write the workflow**

```yaml
name: Deploy

on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_DEPLOY_SA_EMAIL }}

      - uses: google-github-actions/setup-gcloud@v2

      - name: Configure Docker for Artifact Registry
        run: gcloud auth configure-docker "${{ secrets.GCP_REGION }}-docker.pkg.dev" --quiet

      - name: Build and push image
        run: |
          IMAGE="${{ secrets.GCP_REGION }}-docker.pkg.dev/${{ secrets.GCP_PROJECT_ID }}/cosmos/cosmos-app:${{ github.sha }}"
          docker build -t "$IMAGE" .
          docker push "$IMAGE"
          echo "IMAGE=$IMAGE" >> "$GITHUB_ENV"

      - name: Run database migrations
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: |
          python -m pip install -r backend/requirements.txt
          python backend/database.py

      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy cosmos-prod \
            --image "$IMAGE" \
            --region "${{ secrets.GCP_REGION }}" \
            --service-account "${{ secrets.GCP_RUNTIME_SA_EMAIL }}" \
            --set-secrets "DATABASE_URL=DATABASE_URL:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,OPENAI_API_KEY=OPENAI_API_KEY:latest,ADMIN_API_TOKEN=ADMIN_API_TOKEN:latest" \
            --set-env-vars "GCP_PROJECT_ID=${{ secrets.GCP_PROJECT_ID }},GCP_LOCATION=${{ secrets.GCP_REGION }}" \
            --allow-unauthenticated
```

`DATABASE_URL` also needs to be a GitHub repo secret (its value already exists in Secret Manager from Task 4 — add the same value as a GitHub secret too, since the migration step runs from the Actions runner, not from inside Cloud Run) — add it alongside the others.

- [ ] **Step 3: Verify end-to-end**

Merge a small change to `main`. Expected: the `test` job (Task 5) runs first, then `deploy` pauses in GitHub's UI awaiting approval (per Step 1's environment rule); after approving, the job builds, pushes, migrates, and deploys, ending with `gcloud run deploy` printing a `Service URL`. Visiting `<Service URL>/healthz` returns `{"status":"ok"}`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add build/migrate/deploy workflow with manual approval gate"
```

---

### Task 7: Cloud Monitoring alert policies

**Files:** none (infrastructure)

**Interfaces:** none — operational only.

- [ ] **Step 1: Create a notification channel**

```bash
gcloud beta monitoring channels create \
  --display-name="Cosmos ops email" \
  --type=email \
  --channel-labels=email_address=<your-ops-email>
```

Expected: prints the created channel's resource name — copy it for the next steps as `CHANNEL_ID`.

- [ ] **Step 2: Create the error-rate alert policy**

```bash
gcloud alpha monitoring policies create \
  --display-name="Cosmos: high 5xx rate" \
  --condition-display-name="5xx rate > 5% over 5m" \
  --condition-filter='resource.type="cloud_run_revision" AND resource.labels.service_name="cosmos-prod" AND metric.type="run.googleapis.com/request_count" AND metric.labels.response_code_class="5xx"' \
  --condition-threshold-value=0.05 \
  --condition-threshold-duration=300s \
  --notification-channels="$CHANNEL_ID"
```

Expected: prints the created policy's resource name.

- [ ] **Step 3: Document the LLM-failure log-based metric**

This one is best created once via Console (Logging → Logs-based Metrics → Create Metric) since its filter targets the `"Error generating evaluation via"` log line added in the LLM Provider Abstraction plan's Task 9 — record the metric name (`llm_provider_failures`) and wire it to the same notification channel as Step 2 once created; there's no single clean `gcloud` one-liner worth scripting here for a single log-based metric.

---

### Task 8: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `documentation/guides/quick-start.md`
- Modify: `documentation/product/roadmap.md`
- Modify: `CHANGELOG.md`

**Interfaces:** none (docs only)

- [ ] **Step 1: Update `CLAUDE.md` Part 6 (Development Workflow)**

Add a "Production deployment" subsection after the existing "Setup & run" block:
```markdown
**Production deployment**: single Cloud Run service `cosmos-prod` on GCP. Push to `main` triggers CI (`pytest`); on success, the deploy workflow builds the image, runs `backend/database.py` migrations, and waits for manual approval in GitHub's `production` environment before deploying. See `docs/superpowers/specs/2026-08-25-production-deployment-design.md` and `docs/superpowers/plans/2026-08-25-gcp-deployment-infrastructure.md`.
```

- [ ] **Step 2: Update `documentation/guides/quick-start.md`**

Add a note pointing local-dev readers at the production path: "For production deployment (GCP Cloud Run, CI/CD, secrets), see the deployment spec and plan under `docs/superpowers/`; this guide covers local development only."

- [ ] **Step 3: Update `documentation/product/roadmap.md`**

Add a checklist entry under "Foundational Work" (or a new "Production Deployment" section) noting: `- [x] **Production deployment infrastructure**: GCP Cloud Run + CI/CD + multi-provider LLM abstraction shipped ahead of Phase A/B, per the 2026-08-25 deployment spec.` — mark items complete only once Tasks 1-7 here are actually done, not when this plan is merely written.

- [ ] **Step 4: Add a `CHANGELOG.md` entry**

Under `## [Unreleased]` (added by the LLM Provider Abstraction plan's Task 10 — append to the same section rather than creating a second one):
```markdown
### Added
- GCP Cloud Run deployment infrastructure: Dockerfile, GitHub Actions CI/CD with a manual approval gate, Secret Manager secrets, Workload Identity Federation, and Cloud Monitoring alerting.
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md documentation/guides/quick-start.md documentation/product/roadmap.md CHANGELOG.md
git commit -m "docs: document the GCP production deployment infrastructure"
```
