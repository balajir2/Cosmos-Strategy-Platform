import contextlib

from database import get_db_connection
import framework_knowledge_db
from project_knowledge_base import extract_text, chunk_text, _DOCUMENT_EXTENSIONS


def infer_framework_source_format(filename: str) -> str:
    """Like project_knowledge_base.infer_source_format, but documents only -
    Cosmos Knowledge uploads never include audio (see the design spec's
    Non-Goals)."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension in _DOCUMENT_EXTENSIONS:
        return _DOCUMENT_EXTENSIONS[extension]
    raise ValueError(f"Unsupported file extension for Cosmos Knowledge uploads: '.{extension}'")


def _insert_chunks(source_id: int, source_file: str, chunks: list, embeddings) -> None:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            for chunk, embedding in zip(chunks, embeddings):
                cursor.execute(
                    """
                    INSERT INTO framework_kb_chunks (source_file, phase, slide_number, text, embedding, source_id)
                    VALUES (%s, NULL, NULL, %s, %s, %s);
                    """,
                    (source_file, chunk, embedding, source_id),
                )
        conn.commit()


def ingest_framework_source(rag, source_id: int, file_bytes: bytes):
    """Synchronous ingestion for a Cosmos Knowledge upload: extracts text
    (reusing project_knowledge_base.extract_text, the same extractors the
    Engagement KB uses), chunks it, embeds each chunk with rag's
    SentenceTransformer, and inserts framework_kb_chunks rows tagged with
    this source (phase/slide_number left NULL - those only ever apply to
    the two legacy startup-seeded PDFs). Marks the framework_kb_sources row
    'Indexed' on success or 'Failed' if extraction produced no usable text
    or anything raised - mirroring project_knowledge_base.ingest_artifact's
    graceful-degradation shape."""
    source = framework_knowledge_db.get_source_by_id(source_id)
    if source is None:
        raise ValueError(f"Unknown source_id '{source_id}'")

    try:
        text = extract_text(file_bytes, source["source_format"])
        chunks = chunk_text(text)
        if not chunks:
            print(f"Framework Knowledge source {source_id} produced no extractable text.")
            return framework_knowledge_db.update_source_status(source_id, "Failed")

        embeddings = rag.embedding_model.encode(chunks)
        _insert_chunks(source_id, source["filename"], chunks, embeddings)

        return framework_knowledge_db.update_source_status(source_id, "Indexed")
    except Exception as e:
        print(f"Error ingesting Framework Knowledge source {source_id}: {e}")
        return framework_knowledge_db.update_source_status(source_id, "Failed")
