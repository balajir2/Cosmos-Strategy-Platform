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

COPY backend/ backend/
COPY --from=frontend-build /app/frontend-react/out/ frontend-react/out/

ENV PORT=8080
EXPOSE 8080

CMD uvicorn main:app --app-dir /app/backend --host 0.0.0.0 --port ${PORT}
