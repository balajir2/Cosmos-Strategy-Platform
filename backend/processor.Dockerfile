FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements.txt
# See the root Dockerfile's identical comment - same fix, same reason.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD uvicorn processor_main:app --host 0.0.0.0 --port ${PORT}
