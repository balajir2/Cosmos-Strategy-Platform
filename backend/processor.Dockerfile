FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements.txt
# See the root Dockerfile's identical comment - same fix, same reason.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch && \
    pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image at build time. Without this, the
# container downloads it from Hugging Face Hub on every cold start - which
# on Cloud Run got HTTP 429 rate-limited, and HF's own backoff (244s)
# exceeded Cloud Run's startup probe timeout, so the container never bound
# its port in time. Baking it in means zero network calls at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . .

ENV PORT=8080
# Even with the model baked in above, sentence-transformers/huggingface_hub
# still makes a runtime HEAD request to check for updates unless told not
# to - which hit the same HF rate-limit/timeout problem this bake-in was
# meant to fix. HF_HUB_OFFLINE=1 stops it from ever trying.
ENV HF_HUB_OFFLINE=1
EXPOSE 8080

CMD uvicorn processor_main:app --host 0.0.0.0 --port ${PORT}
