"""Offline checks for text recognition (OCR): scanned PDF pages and image uploads
(AI client mocked, temp uploads dir, storage mocked; no DB, Chroma data or network).

Run from backend/:  .venv/Scripts/python.exe tests/test_ocr.py
"""
import asyncio
import base64
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database, vector store, model hub or OpenRouter.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

import fitz
import httpx
import openai
from fastapi import HTTPException, UploadFile
from PIL import Image

from app.api import upload
from app.services.ai import summary_service
from app.services.ai.flashcard_service import build_chunk_citations
from app.services.ai.merged_service import SOURCE_KINDS
from app.services.ai.summary_service import AIGenerationError
from app.services.ocr import ocr_service

TEST_USER = SimpleNamespace(id=1)


# ─── helpers ───

def reply(text, finish_reason="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish_reason)])


def status_error(code, message="boom"):
    return openai.APIStatusError(
        f"Error code: {code} - {message}",
        response=httpx.Response(code, request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")),
        body=None,
    )


class FakeClient:
    """Stands in for the OpenAI client: replies in turn (an exception is raised), records calls."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(item, BaseException):
            raise item
        return item if not isinstance(item, str) else reply(item)


def image_bytes(fmt="PNG", size=(60, 40), mode="RGB", color=(200, 30, 30), exif_orientation=None):
    image = Image.new(mode, size, color if mode != "RGBA" else (0, 0, 0, 0))
    buf = io.BytesIO()
    kwargs = {}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kwargs["exif"] = exif
    image.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def pdf_bytes(pages):
    """pages: list of "text" (a text page), "scan" (an image, no text) or "" (blank)."""
    doc = fitz.open()
    for kind in pages:
        page = doc.new_page()
        if kind == "scan":
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), False)
            pix.clear_with(200)
            page.insert_image(fitz.Rect(40, 40, 400, 400), stream=pix.tobytes("png"))
        elif kind:
            page.insert_textbox(fitz.Rect(40, 40, 560, 800), kind, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def run(coro_fn, files, ocr_client=None, store=None):
    """Run an upload endpoint against a temp uploads dir with storage and the OCR client mocked.

    Returns (result or HTTPException, files left, store mock).
    """
    tmp = Path(tempfile.mkdtemp(prefix="sb-test-uploads-"))
    store = store or MagicMock(side_effect=lambda **kw: {"status": "stored", **kw})
    with patch.object(upload, "UPLOAD_DIR", tmp), patch.object(upload, "_store_document_and_chunks", store), \
         patch.object(upload, "logger"), patch.object(ocr_service, "logger"), patch.object(summary_service, "logger"), \
         patch.object(ocr_service, "client", ocr_client or FakeClient("unused")), \
         patch.object(summary_service, "RETRY_DELAY_SECONDS", 0), patch.object(ocr_service, "RETRY_DELAY_SECONDS", 0):
        try:
            result = asyncio.run(coro_fn(files, db=MagicMock(), user=TEST_USER))
        except HTTPException as e:
            result = e
    return result, sorted(p.name for p in tmp.iterdir()), store


def pdf_upload(data, name="notes.pdf"):
    return lambda files, **kw: upload.upload_pdf(file=UploadFile(file=io.BytesIO(data), filename=name), **kw)


def images_upload(items):
    return lambda files, **kw: upload.upload_images(
        files=[UploadFile(file=io.BytesIO(d), filename=n) for n, d in items], **kw
    )


def rejected(result, status, contains=None):
    assert isinstance(result, HTTPException), f"expected an error, got {result!r}"
    assert result.status_code == status, (result.status_code, result.detail)
    if contains is not None:
        assert contains in result.detail, result.detail


# ─── the OCR service ───

def test_default_model_is_a_free_vision_model():
    assert ocr_service.DEFAULT_OCR_MODEL.endswith(":free")
    assert ocr_service.OCR_MODEL  # OCR_MODEL from .env, or the default


def test_prepare_image_makes_an_upright_jpeg():
    jpeg = ocr_service.prepare_image(image_bytes("PNG"))
    assert jpeg[:2] == b"\xff\xd8"
    # Transparent PNG screenshots go on white, not black.
    with Image.open(io.BytesIO(ocr_service.prepare_image(image_bytes("PNG", mode="RGBA")))) as img:
        assert img.getpixel((5, 5))[0] > 240, img.getpixel((5, 5))
    # A phone photo stored sideways (EXIF orientation 6) is turned upright: 60×40 -> 40×60.
    with Image.open(io.BytesIO(ocr_service.prepare_image(image_bytes("JPEG", exif_orientation=6)))) as img:
        assert img.size == (40, 60), img.size
    # Big images are shrunk to MAX_IMAGE_SIDE.
    with Image.open(io.BytesIO(ocr_service.prepare_image(image_bytes("JPEG", size=(4000, 1000))))) as img:
        assert max(img.size) == ocr_service.MAX_IMAGE_SIDE, img.size


def test_prepare_image_refuses_other_files():
    for data in (b"not an image", image_bytes("GIF"), image_bytes("PNG")[:40]):
        try:
            ocr_service.prepare_image(data)
            raise AssertionError("should have refused")
        except ocr_service.ImageFileError:
            pass


def test_ocr_image_sends_the_image_to_the_ocr_model():
    client = FakeClient("```\nNewton's second law\nF = ma\n```")
    with patch.object(ocr_service, "client", client):
        text = ocr_service.ocr_image(b"\xff\xd8jpeg")
    assert text == "Newton's second law\nF = ma", text
    call = client.calls[0]
    assert call["model"] == ocr_service.OCR_MODEL
    content = call["messages"][0]["content"]
    url = next(part["image_url"]["url"] for part in content if part["type"] == "image_url")
    assert url == "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8jpeg").decode()


def test_ocr_image_no_text_is_empty_not_an_error():
    for answer in ("", "   ", "Nothing", "[No text]"):
        with patch.object(ocr_service, "client", FakeClient(reply(answer))):
            assert ocr_service.ocr_image(b"x") == "", answer


def test_ocr_image_retries_temporary_failures_only():
    client = FakeClient(status_error(503), "Text")
    with patch.object(ocr_service, "client", client), patch.object(ocr_service, "RETRY_DELAY_SECONDS", 0), \
         patch.object(ocr_service, "logger"):
        assert ocr_service.ocr_image(b"x") == "Text"
    assert len(client.calls) == 2

    client = FakeClient(status_error(402))
    with patch.object(ocr_service, "client", client), patch.object(summary_service, "logger"):
        try:
            ocr_service.ocr_image(b"x")
            raise AssertionError("should fail")
        except AIGenerationError as e:
            assert "out of credits" in str(e)
    assert len(client.calls) == 1

    # An error sent inside a 200 reply counts as that error.
    client = FakeClient(SimpleNamespace(choices=[], error={"code": 404, "message": "No endpoints"}))
    with patch.object(ocr_service, "client", client), patch.object(ocr_service, "logger"):
        try:
            ocr_service.ocr_image(b"x")
            raise AssertionError("should fail")
        except AIGenerationError as e:
            # Points at OCR_MODEL, not the summary model's setting.
            assert "OCR_MODEL" in str(e) and ocr_service.OCR_MODEL in str(e), str(e)
            assert "OPENROUTER_MODEL" not in str(e)


def test_ocr_images_keeps_the_order():
    client = FakeClient("unused")
    client.create = lambda **kw: reply(kw["messages"][0]["content"][1]["image_url"]["url"][-8:])
    client.chat = SimpleNamespace(completions=SimpleNamespace(create=client.create))
    jpegs = [f"image-{i:02d}".encode() for i in range(6)]
    with patch.object(ocr_service, "client", client):
        texts = ocr_service.ocr_images(jpegs)
    assert texts == [base64.b64encode(j).decode()[-8:] for j in jpegs], texts


# ─── scanned PDF pages ───

def test_scanned_pages_are_found():
    data = pdf_bytes(["Real text here.", "scan", "", "scan"])
    assert upload.PDFService.scanned_pages(data) == [2, 4]
    pics = upload.PDFService.render_pages(data, [2, 4])
    assert len(pics) == 2 and all(p[:2] == b"\xff\xd8" for p in pics)


def test_pdf_with_text_only_makes_no_ocr_call():
    client = FakeClient("should not be called")
    result, left, store = run(pdf_upload(pdf_bytes(["Mitochondria make ATP. " * 5])), None, client)
    assert result["status"] == "stored", result
    assert client.calls == []
    assert store.call_args.kwargs["metadata_json"] is None
    assert len(left) == 1


def test_scanned_pages_are_read_in_place_with_their_page_numbers():
    # Long pages, so each page makes chunks of its own.
    client = FakeClient("Photosynthesis happens in chloroplasts and turns light into chemical energy. " * 20)
    data = pdf_bytes(["Mitochondria make ATP by oxidative phosphorylation. " * 20, "scan", "Ribosomes build proteins. " * 30])
    result, left, store = run(pdf_upload(data), None, client)
    assert result["status"] == "stored", result
    assert len(client.calls) == 1  # only page 2 needed OCR
    kw = store.call_args.kwargs
    assert kw["source_type"] == "pdf"
    assert "Photosynthesis" in kw["content"] and "Mitochondria" in kw["content"] and "Ribosomes" in kw["content"]
    # The OCR text is cited as page 2.
    spans = list(zip(kw["chunks"], kw["chunk_pages"]))
    assert all(start <= 2 <= end for text, (start, end) in spans if "Photosynthesis" in text), spans
    assert any(pages == (2, 2) for _, pages in spans), [p for _, p in spans]
    assert all("Photosynthesis" not in text for text, pages in spans if pages in ((1, 1), (3, 3)))
    assert json.loads(kw["metadata_json"])["ocr_pages"] == [2]
    assert len(left) == 1


def test_fully_scanned_pdf_is_read():
    client = FakeClient("Page text from the scan.")
    result, _, store = run(pdf_upload(pdf_bytes(["scan", "scan"])), None, client)
    assert result["status"] == "stored", result
    assert len(client.calls) == 2
    assert store.call_args.kwargs["chunk_pages"][0][0] == 1
    assert store.call_args.kwargs["chunk_pages"][-1][1] == 2


def test_more_than_20_scanned_pages_is_refused_before_any_ocr():
    client = FakeClient("unused")
    result, left, _ = run(pdf_upload(pdf_bytes(["Some text."] + ["scan"] * 21)), None, client)
    rejected(result, 400, "limited to 20 pages")
    assert "21" in result.detail
    assert client.calls == [] and left == []
    # 20 scanned pages is fine.
    result, _, _ = run(pdf_upload(pdf_bytes(["scan"] * 20)), None, FakeClient("Scanned words."))
    assert result["status"] == "stored", result


def test_ocr_failure_is_a_502_and_removes_the_file():
    result, left, _ = run(pdf_upload(pdf_bytes(["scan"])), None, FakeClient(status_error(401)))
    rejected(result, 502, "Text recognition failed")
    assert "API key" in result.detail
    assert left == []


def test_scan_with_no_recognisable_text():
    result, left, _ = run(pdf_upload(pdf_bytes(["scan"])), None, FakeClient(""))
    rejected(result, 400)
    assert result.detail == upload.SCANNED_PDF_MESSAGE
    assert left == []
    # A blank PDF (no images) keeps its own message and makes no OCR call.
    client = FakeClient("unused")
    result, _, _ = run(pdf_upload(pdf_bytes([""])), None, client)
    rejected(result, 400)
    assert result.detail == "No readable text found in this PDF file"
    assert client.calls == []


# ─── image uploads ───

def test_images_become_one_document_one_page_each():
    client = FakeClient("Cell membrane controls what enters the cell.", "Nucleus holds the DNA of the cell.")
    result, left, store = run(images_upload([("board.jpg", image_bytes("JPEG")), ("notes.png", image_bytes("PNG"))]), None, client)
    assert result["status"] == "stored", result
    kw = store.call_args.kwargs
    assert kw["source_type"] == "image"
    assert kw["filename"] == "board.jpg + 1 more image"
    assert "Cell membrane" in kw["content"] and "Nucleus" in kw["content"]
    pages = dict(zip(kw["chunks"], kw["chunk_pages"]))
    assert [p for t, p in pages.items() if "Nucleus" in t][0][1] == 2
    assert [p for t, p in pages.items() if "Cell membrane" in t][0][0] == 1
    assert json.loads(kw["metadata_json"])["images"] == ["board.jpg", "notes.png"]
    # Both originals kept, named so deleting the document ("{file_id}.*") removes them.
    file_id = kw["file_id"]
    assert left == [f"{file_id}.1.jpg", f"{file_id}.2.png"], left
    assert all(p.startswith(f"{file_id}.") for p in left)
    assert len(client.calls) == 2


def test_single_image_keeps_its_name():
    result, _, store = run(images_upload([("Lecture 3.png", image_bytes())]), None, FakeClient("Some notes on enzymes."))
    assert result["status"] == "stored", result
    assert store.call_args.kwargs["filename"] == "Lecture 3.png"
    assert run(images_upload([("a.png", image_bytes())] * 3), None, FakeClient("Words."))[2] \
        .call_args.kwargs["filename"] == "a.png + 2 more images"


def test_image_upload_limits_and_bad_files():
    client = FakeClient("unused")
    result, left, _ = run(images_upload([("a.png", image_bytes())] * 21), None, client)
    rejected(result, 400, "limited to 20 pages")
    assert left == [] and client.calls == []

    result, left, _ = run(images_upload([("a.png", image_bytes()), ("b.gif", image_bytes("GIF"))]), None, client)
    rejected(result, 400, '"b.gif" isn\'t a JPEG or PNG image')
    assert left == []

    result, left, _ = run(images_upload([("a.png", b"not really a png")]), None, client)
    rejected(result, 400, '"a.png" can\'t be read')
    assert left == [] and client.calls == []

    with patch.object(upload, "MAX_FILE_SIZE", 10):
        result, left, _ = run(images_upload([("a.png", image_bytes())]), None, client)
    rejected(result, 400, "too large")
    with patch.object(upload, "MAX_IMAGES_TOTAL_SIZE", 100):
        result, left, _ = run(images_upload([("a.png", image_bytes()), ("b.png", image_bytes())]), None, client)
    rejected(result, 400, "too large together")
    assert client.calls == []


def test_image_upload_failures_remove_the_files():
    result, left, _ = run(images_upload([("a.png", image_bytes()), ("b.png", image_bytes())]), None, FakeClient(status_error(429)))
    rejected(result, 502, "Text recognition failed")
    assert left == [], left

    result, left, _ = run(images_upload([("a.png", image_bytes())]), None, FakeClient(""))
    rejected(result, 400)
    assert result.detail == upload.NO_TEXT_IN_IMAGES_MESSAGE
    assert left == []

    result, left, _ = run(images_upload([("a.png", image_bytes())]), None, FakeClient("Fine text."),
                          store=MagicMock(side_effect=HTTPException(status_code=502, detail="embeddings")))
    rejected(result, 502)
    assert left == []


# ─── citations for image documents ───

def test_image_documents_cite_pages():
    citations = build_chunk_citations("image", None, "board.jpg", [("a", None), ("b", None)], pages=[(1, 1), (1, 2)])
    assert citations == [("p. 1", None), ("pp. 1–2", None)], citations
    assert SOURCE_KINDS["image"] == "Images"


def test_search_gives_image_matches_a_page():
    from app.services import search_service
    fake = MagicMock()
    fake.query.return_value = {
        "ids": [["9-0"]], "documents": [["text"]], "distances": [[0.2]],
        "metadatas": [[{"filename": "board.jpg", "source_type": "image", "page_start": 2, "page_end": 2}]],
    }
    with patch.object(search_service, "get_collection", return_value=fake), \
         patch.object(search_service, "get_embedding", return_value=[0.0] * 3):
        results = search_service.search_similar_chunks("q", 1)
    assert results[0][6] == "p. 2", results


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
