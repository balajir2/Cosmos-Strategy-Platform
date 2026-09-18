# Stage 1: build the Next.js static export
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend-react
COPY frontend-react/package.json frontend-react/package-lock.json ./
RUN npm ci
COPY frontend-react/ ./
# NEXT_PUBLIC_* values are inlined into the JS bundle at build time, not read
# at runtime - a static export has no server to substitute them later. Empty
# string means same-origin relative API calls (api-client.ts reads this via
# `process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"` - the `??`,
# not `||`, so this empty string is used as-is instead of falling through to
# that fallback), which is exactly right for this single-service deployment:
# FastAPI serves this same export, so /api/* already resolves against the
# same host.
# Left unset, api-client.ts's own fallback bakes in http://localhost:8000,
# which is only reachable from whoever happens to be running the backend
# locally - found and fixed after the first deploy shipped with that bug.
ENV NEXT_PUBLIC_API_BASE=""
RUN npm run build

# Stage 2: Python runtime, serving both the API and the static export
FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
# CPU-only torch: sentence-transformers pulls in torch as a dependency, and
# pip's default wheel for it bundles the full NVIDIA CUDA runtime (~3.2GB)
# plus the triton GPU kernel compiler (~900MB), even though nothing in this
# image ever runs on a GPU. Installing the CPU-only build first satisfies
# that dependency before requirements.txt would otherwise pull in the CUDA
# one - this alone cut the built image from ~10.1GB to ~2.49GB, meaningfully
# faster Cloud Run cold starts at min-instances=0.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch && \
    pip install --no-cache-dir -r backend/requirements.txt

# Bake the embedding model into the image at build time. Without this, the
# container downloads it from Hugging Face Hub on every cold start - which
# on Cloud Run got HTTP 429 rate-limited, and HF's own backoff (244s)
# exceeded Cloud Run's startup probe timeout, so the container never bound
# its port in time (discovered deploying cosmos-artifact-processor; RagEngine
# here loads the same model the same way, so it would hit the same failure).
# Baking it in means zero network calls at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY backend/ backend/
COPY --from=frontend-build /app/frontend-react/out/ frontend-react/out/

ENV PORT=8080
# Even with the model baked in above, sentence-transformers/huggingface_hub
# still makes a runtime HEAD request to check for updates unless told not
# to - which hit the same HF rate-limit/timeout problem this bake-in was
# meant to fix. HF_HUB_OFFLINE=1 stops it from ever trying.
ENV HF_HUB_OFFLINE=1
EXPOSE 8080

# exec form via `sh -c ... exec` so uvicorn is PID 1's direct child and
# actually receives SIGTERM - Cloud Run's shutdown signal - instead of it
# being swallowed by a shell that doesn't forward it, which would otherwise
# kill in-flight requests at the grace-period deadline rather than draining.
CMD ["sh", "-c", "exec uvicorn main:app --app-dir /app/backend --host 0.0.0.0 --port ${PORT}"]
