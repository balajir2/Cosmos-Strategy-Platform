import contextlib
import io
import os
import time
import uuid

from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import speech, storage
from docx import Document
from pptx import Presentation
from pypdf import PdfReader
from openpyxl import load_workbook

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


def extract_text_from_xlsx(file_bytes: bytes, max_chunk_chars: int = 1000, max_cell_chars: int = 500) -> str:
    """Renders each row as 'Col: val, Col: val, ...' and packs consecutive
    rows into ~max_chunk_chars-sized paragraphs (each paragraph becomes one
    chunk_text() chunk), never splitting a single row across two chunks -
    cheaper on both embedding compute and Neon storage than one chunk per
    row, and more retrieval-precise than one chunk per sheet. Individual cell
    values are capped at max_cell_chars, and assembled row strings are clamped
    to max_chunk_chars, guaranteeing no row ever exceeds the pack budget."""
    workbook = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    packs = []
    for sheet in workbook.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(c).strip() if c is not None else "" for c in rows[0]]
        current_pack = []
        current_len = 0
        for data_row in rows[1:]:
            if all(cell is None for cell in data_row):
                continue
            rendered = ", ".join(
                f"{header[i]}: {str(cell)[:max_cell_chars]}{'...' if len(str(cell)) > max_cell_chars else ''}"
                for i, cell in enumerate(data_row)
                if i < len(header) and cell is not None
            )
            if not rendered:
                continue
            # Clamp the entire row string if it exceeds max_chunk_chars, preventing
            # multi-column overflow from exceeding the pack budget (e.g. several
            # medium columns summing to >1000 chars, each individually under cap).
            # Reserve 3 chars for the truncation marker so the clamped row doesn't
            # exceed the pack budget.
            if len(rendered) > max_chunk_chars:
                rendered = rendered[:max_chunk_chars - 3] + "..."
            if current_pack and current_len + len(rendered) + 1 > max_chunk_chars:
                packs.append("\n".join(current_pack))
                current_pack, current_len = [], 0
            current_pack.append(rendered)
            current_len += len(rendered) + 1
        if current_pack:
            packs.append("\n".join(current_pack))
    return "\n\n".join(packs)


_EXTRACTORS = {
    "pdf": extract_text_from_pdf,
    "docx": extract_text_from_docx,
    "pptx": extract_text_from_pptx,
    "txt": extract_text_from_txt,
    "md": extract_text_from_txt,
    "xlsx": extract_text_from_xlsx,
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


_DOCUMENT_EXTENSIONS = {"pdf": "pdf", "docx": "docx", "pptx": "pptx", "txt": "txt", "md": "md", "xlsx": "xlsx"}
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

_SPEECH_ENCODING_BY_EXTENSION = {
    "mp3": speech.RecognitionConfig.AudioEncoding.MP3,
    "wav": speech.RecognitionConfig.AudioEncoding.LINEAR16,
    "flac": speech.RecognitionConfig.AudioEncoding.FLAC,
    "ogg": speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
}


def transcribe_audio(file_bytes: bytes, filename: str):
    """Transcribes an audio artifact via Google Cloud Speech-to-Text. Returns
    the transcript text, or None if GCS isn't configured, the format isn't
    supported, or the job fails - mirroring rag_engine.py's graceful-degradation
    philosophy (missing external-service configuration skips the automatic path
    rather than crashing the upload). Callers should set the artifact's status
    to 'Transcript Needed' (not 'Failed') when this returns None, so a
    Consultant can paste a transcript manually instead."""
    bucket_name = os.environ.get("GCS_TRANSCRIBE_BUCKET")
    if not bucket_name:
        print("GCS_TRANSCRIBE_BUCKET is not set. Skipping automatic transcription.")
        return None

    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    encoding = _SPEECH_ENCODING_BY_EXTENSION.get(extension)
    if encoding is None:
        print(f"Unsupported audio format '.{extension}' for automatic transcription. Skipping.")
        return None

    job_name = f"cosmos-transcribe-{uuid.uuid4().hex}"
    blob_name = f"transcribe-uploads/{job_name}.{extension}"

    try:
        bucket = storage.Client().bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(file_bytes)

        speech_client = speech.SpeechClient()
        config = speech.RecognitionConfig(
            encoding=encoding,
            language_code="en-US",
            enable_automatic_punctuation=True,
        )
        audio = speech.RecognitionAudio(uri=f"gs://{bucket_name}/{blob_name}")
        operation = speech_client.long_running_recognize(config=config, audio=audio)

        for _ in range(_TRANSCRIBE_MAX_POLL_ATTEMPTS):
            if operation.done():
                response = operation.result()
                transcript = " ".join(
                    result.alternatives[0].transcript
                    for result in response.results
                    if result.alternatives
                ).strip()
                return transcript or None
            time.sleep(_TRANSCRIBE_POLL_INTERVAL_SECONDS)

        print(f"Google Speech-to-Text job '{job_name}' did not complete within the polling window.")
        return None
    except (GoogleAPICallError, DefaultCredentialsError, ValueError, KeyError, IndexError) as e:
        print(f"Google Speech-to-Text unavailable ({e}). Falling back to manual transcript entry.")
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
    error OR when extraction produced no usable text (an artifact marked
    'Indexed' with zero project_kb_chunks rows would silently never surface
    in retrieval with no visible signal that anything went wrong). Runs
    inline on the upload request - no background job queue, per the spec's
    "Synchronous for now" decision."""
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
        if not chunks:
            print(f"Artifact {artifact_id} produced no extractable text.")
            return project_artifacts_db.update_artifact_status(artifact_id, "Failed")

        embeddings = rag.embedding_model.encode(chunks)
        _insert_chunks(artifact["project_id"], artifact_id, chunks, embeddings)

        transcript_text = text if artifact["source_format"] == "audio" else None
        return project_artifacts_db.update_artifact_status(artifact_id, "Indexed", transcript_text=transcript_text)
    except Exception as e:
        print(f"Error ingesting artifact {artifact_id}: {e}")
        return project_artifacts_db.update_artifact_status(artifact_id, "Failed")
