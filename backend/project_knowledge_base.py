import io

from docx import Document
from pptx import Presentation
from pypdf import PdfReader


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
