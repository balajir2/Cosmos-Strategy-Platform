# Stage 1: build the Next.js static export
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend-react
COPY frontend-react/package.json frontend-react/package-lock.json ./
RUN npm ci
COPY frontend-react/ ./
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
# one - this alone cut the built image from ~10.1GB to a few GB smaller,
# meaningfully faster Cloud Run cold starts at min-instances=0.
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

CMD uvicorn main:app --app-dir /app/backend --host 0.0.0.0 --port ${PORT}
