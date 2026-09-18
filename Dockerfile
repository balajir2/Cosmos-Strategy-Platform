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
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY --from=frontend-build /app/frontend-react/out/ frontend-react/out/

ENV PORT=8080
EXPOSE 8080

CMD uvicorn main:app --app-dir /app/backend --host 0.0.0.0 --port ${PORT}
