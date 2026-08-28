import io
from unittest.mock import MagicMock, patch

import pytest
from docx import Document
from pptx import Presentation
from pptx.util import Inches

import project_knowledge_base as pkb


def _docx_bytes(paragraphs):
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pptx_bytes(slide_texts):
    prs = Presentation()
    layout = prs.slide_layouts[6]
    for text in slide_texts:
        slide = prs.slides.add_slide(layout)
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        box.text_frame.text = text
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_extract_text_from_docx_joins_paragraphs():
    file_bytes = _docx_bytes(["First paragraph.", "Second paragraph."])

    result = pkb.extract_text_from_docx(file_bytes)

    assert result == "First paragraph.\n\nSecond paragraph."


def test_extract_text_from_pptx_joins_slide_text():
    file_bytes = _pptx_bytes(["Slide one text", "Slide two text"])

    result = pkb.extract_text_from_pptx(file_bytes)

    assert "Slide one text" in result
    assert "Slide two text" in result


def test_extract_text_from_txt_decodes_utf8():
    result = pkb.extract_text_from_txt("Hello world".encode("utf-8"))
    assert result == "Hello world"


@patch("project_knowledge_base.PdfReader")
def test_extract_text_from_pdf_joins_page_text(mock_reader_cls):
    page1, page2 = MagicMock(), MagicMock()
    page1.extract_text.return_value = "Page one text"
    page2.extract_text.return_value = "Page two text"
    mock_reader_cls.return_value.pages = [page1, page2]

    result = pkb.extract_text_from_pdf(b"fake-pdf-bytes")

    assert result == "Page one text\n\nPage two text"


def test_extract_text_dispatches_on_source_format():
    result = pkb.extract_text("Hello world".encode("utf-8"), "txt")
    assert result == "Hello world"


def test_extract_text_raises_on_unsupported_format():
    with pytest.raises(ValueError, match="audio"):
        pkb.extract_text(b"data", "audio")


def test_chunk_text_splits_on_paragraph_breaks():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."

    result = pkb.chunk_text(text)

    assert result == ["First paragraph.", "Second paragraph.", "Third paragraph."]


def test_chunk_text_splits_long_paragraph_into_fixed_size_pieces():
    long_paragraph = "x" * 2500

    result = pkb.chunk_text(long_paragraph, max_chunk_chars=1000)

    assert result == ["x" * 1000, "x" * 1000, "x" * 500]


def test_infer_source_format_maps_known_document_extensions():
    assert pkb.infer_source_format("report.pdf") == "pdf"
    assert pkb.infer_source_format("notes.docx") == "docx"
    assert pkb.infer_source_format("deck.pptx") == "pptx"
    assert pkb.infer_source_format("transcript.txt") == "txt"


def test_infer_source_format_maps_audio_extensions():
    assert pkb.infer_source_format("meeting.mp3") == "audio"
    assert pkb.infer_source_format("call.wav") == "audio"


def test_infer_source_format_raises_on_unsupported_extension():
    with pytest.raises(ValueError, match="exe"):
        pkb.infer_source_format("virus.exe")


def test_infer_artifact_type_maps_audio_and_document():
    assert pkb.infer_artifact_type("audio") == "audio"
    assert pkb.infer_artifact_type("pdf") == "document"
    assert pkb.infer_artifact_type("docx") == "document"


from botocore.exceptions import NoCredentialsError


def test_transcribe_audio_skips_when_bucket_not_configured(monkeypatch):
    monkeypatch.delenv("AWS_TRANSCRIBE_S3_BUCKET", raising=False)

    with patch("project_knowledge_base.boto3.client") as mock_client:
        result = pkb.transcribe_audio(b"fake-audio-bytes", "meeting.mp3")

    assert result is None
    mock_client.assert_not_called()


@patch("project_knowledge_base.boto3.client")
def test_transcribe_audio_returns_none_when_credentials_missing(mock_client, monkeypatch):
    monkeypatch.setenv("AWS_TRANSCRIBE_S3_BUCKET", "cosmos-transcribe-bucket")
    mock_client.side_effect = NoCredentialsError()

    result = pkb.transcribe_audio(b"fake-audio-bytes", "meeting.mp3")

    assert result is None


@patch("project_knowledge_base._fetch_transcript_text", return_value="hello from the meeting")
@patch("project_knowledge_base.boto3.client")
def test_transcribe_audio_returns_transcript_on_completed_job(mock_client, mock_fetch, monkeypatch):
    monkeypatch.setenv("AWS_TRANSCRIBE_S3_BUCKET", "cosmos-transcribe-bucket")

    mock_s3 = MagicMock()
    mock_transcribe = MagicMock()
    mock_transcribe.get_transcription_job.return_value = {
        "TranscriptionJob": {
            "TranscriptionJobStatus": "COMPLETED",
            "Transcript": {"TranscriptFileUri": "https://example.com/transcript.json"},
        }
    }
    mock_client.side_effect = lambda service_name: mock_s3 if service_name == "s3" else mock_transcribe

    result = pkb.transcribe_audio(b"fake-audio-bytes", "meeting.mp3")

    assert result == "hello from the meeting"
    mock_s3.put_object.assert_called_once()
    mock_transcribe.start_transcription_job.assert_called_once()


@patch("project_knowledge_base.boto3.client")
def test_transcribe_audio_returns_none_when_job_fails(mock_client, monkeypatch):
    monkeypatch.setenv("AWS_TRANSCRIBE_S3_BUCKET", "cosmos-transcribe-bucket")

    mock_s3 = MagicMock()
    mock_transcribe = MagicMock()
    mock_transcribe.get_transcription_job.return_value = {
        "TranscriptionJob": {"TranscriptionJobStatus": "FAILED"}
    }
    mock_client.side_effect = lambda service_name: mock_s3 if service_name == "s3" else mock_transcribe

    result = pkb.transcribe_audio(b"fake-audio-bytes", "meeting.mp3")

    assert result is None
