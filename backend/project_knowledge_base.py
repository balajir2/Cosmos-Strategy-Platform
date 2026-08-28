import contextlib
import io
import json
import os
import time
import urllib.error
import urllib.request
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from docx import Document
from pptx import Presentation
from pypdf import PdfReader

from database import get_db_connection
import project_artifacts_db


def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    texts = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(t.strip() for t in texts if t.strip())


def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    return "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


def extract_text_from_pptx(file_bytes: bytes) -> str:
    prs = Presentation(io.BytesIO(file_bytes))
    slide_texts = []
    for slide in prs.slides:
        shape_texts = [
            shape.text_frame.text.strip()
            for shape in slide.shapes
            if shape.has_text_frame and shape.text_frame.text.strip()
        ]
        if shape_texts:
            slide_texts.append("\n".join(shape_texts))
    return "\n\n".join(slide_texts)


def extract_text_from_txt(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8").strip()


_EXTRACTORS = {
    "pdf": extract_text_from_pdf,
    "docx": extract_text_from_docx,
    "pptx": extract_text_from_pptx,
    "txt": extract_text_from_txt,
}


def extract_text(file_bytes: bytes, source_format: str) -> str:
    extractor = _EXTRACTORS.get(source_format)
    if extractor is None:
        raise ValueError(f"Unsupported source_format for text extraction: '{source_format}'")
    return extractor(file_bytes)


def chunk_text(text: str, max_chunk_chars: int = 1000) -> list:
    """Simple paragraph-based chunking, matching rag_engine.py's per-slide
    granularity for the Framework Knowledge Base rather than a more
    sophisticated sentence-aware splitter. Paragraphs longer than
    max_chunk_chars are further split into fixed-size pieces so no single
    chunk overwhelms the embedding model's practical input size."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chunk_chars:
            chunks.append(paragraph)
        else:
            for i in range(0, len(paragraph), max_chunk_chars):
                chunks.append(paragraph[i:i + max_chunk_chars])
    return chunks


_DOCUMENT_EXTENSIONS = {"pdf": "pdf", "docx": "docx", "pptx": "pptx", "txt": "txt"}
_AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "flac", "ogg"}


def infer_source_format(filename: str) -> str:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension in _DOCUMENT_EXTENSIONS:
        return _DOCUMENT_EXTENSIONS[extension]
    if extension in _AUDIO_EXTENSIONS:
        return "audio"
    raise ValueError(f"Unsupported file extension: '.{extension}'")


def infer_artifact_type(source_format: str) -> str:
    return "audio" if source_format == "audio" else "document"


_TRANSCRIBE_POLL_INTERVAL_SECONDS = 5
_TRANSCRIBE_MAX_POLL_ATTEMPTS = 60


def _fetch_transcript_text(transcript_uri: str) -> str:
    with urllib.request.urlopen(transcript_uri) as response:
        payload = json.loads(response.read())
    return payload["results"]["transcripts"][0]["transcript"]


def transcribe_audio(file_bytes: bytes, filename: str):
    """Transcribes an audio artifact via AWS Transcribe. Returns the transcript
    text, or None if AWS isn't configured or the job fails - mirroring
    rag_engine.py's graceful-degradation philosophy (missing external-service
    configuration skips the automatic path rather than crashing the upload).
    Callers should set the artifact's status to 'Transcript Needed' (not
    'Failed') when this returns None, so a Consultant can paste a transcript
    manually instead."""
    bucket = os.environ.get("AWS_TRANSCRIBE_S3_BUCKET")
    if not bucket:
        print("AWS_TRANSCRIBE_S3_BUCKET is not set. Skipping automatic transcription.")
        return None

    job_name = f"cosmos-transcribe-{uuid.uuid4().hex}"
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp3"
    key = f"transcribe-uploads/{job_name}.{extension}"

    try:
        s3 = boto3.client("s3")
        s3.put_object(Bucket=bucket, Key=key, Body=file_bytes)

        transcribe = boto3.client("transcribe")
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": f"s3://{bucket}/{key}"},
            MediaFormat=extension,
            LanguageCode="en-US",
        )

        for _ in range(_TRANSCRIBE_MAX_POLL_ATTEMPTS):
            status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            job_status = status["TranscriptionJob"]["TranscriptionJobStatus"]
            if job_status == "COMPLETED":
                transcript_uri = status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                return _fetch_transcript_text(transcript_uri)
            if job_status == "FAILED":
                print(f"AWS Transcribe job '{job_name}' failed.")
                return None
            time.sleep(_TRANSCRIBE_POLL_INTERVAL_SECONDS)

        print(f"AWS Transcribe job '{job_name}' did not complete within the polling window.")
        return None
    except (
        BotoCoreError, ClientError, NoCredentialsError,
        urllib.error.URLError, ValueError, KeyError, IndexError,
    ) as e:
        print(f"AWS Transcribe unavailable ({e}). Falling back to manual transcript entry.")
        return None


def _insert_chunks(project_id: int, artifact_id: int, chunks: list, embeddings) -> None:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            for chunk, embedding in zip(chunks, embeddings):
                cursor.execute(
                    """
                    INSERT INTO project_kb_chunks (project_id, artifact_id, chunk_text, embedding)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (project_id, artifact_id, chunk, embedding),
                )
        conn.commit()


def ingest_artifact(rag, artifact_id: int, file_bytes: bytes) -> dict:
    """Synchronous ingestion pipeline: parses or transcribes the uploaded
    artifact, chunks the resulting text, embeds each chunk with the same
    SentenceTransformer rag_engine.py already uses for the Framework
    Knowledge Base (via rag.embedding_model - loaded once, not duplicated),
    and inserts rows into project_kb_chunks. Updates project_artifacts.status
    to reflect the outcome: 'Indexed' on success, 'Transcript Needed' for
    audio when AWS Transcribe isn't available (never 'Failed' for that case -
    see transcribe_audio's docstring), 'Failed' on any other parse/embedding
    error. Runs inline on the upload request - no background job queue,
    per the spec's "Synchronous for now" decision."""
    artifact = project_artifacts_db.get_artifact_by_id(artifact_id)
    if artifact is None:
        raise ValueError(f"Unknown artifact_id '{artifact_id}'")

    project_artifacts_db.update_artifact_status(artifact_id, "Processing")

    try:
        if artifact["source_format"] == "audio":
            transcript = transcribe_audio(file_bytes, artifact["filename"])
            if transcript is None:
                return project_artifacts_db.update_artifact_status(artifact_id, "Transcript Needed")
            text = transcript
        else:
            text = extract_text(file_bytes, artifact["source_format"])

        chunks = chunk_text(text)
        if chunks:
            embeddings = rag.embedding_model.encode(chunks)
            _insert_chunks(artifact["project_id"], artifact_id, chunks, embeddings)

        transcript_text = text if artifact["source_format"] == "audio" else None
        return project_artifacts_db.update_artifact_status(artifact_id, "Indexed", transcript_text=transcript_text)
    except Exception as e:
        print(f"Error ingesting artifact {artifact_id}: {e}")
        return project_artifacts_db.update_artifact_status(artifact_id, "Failed")
