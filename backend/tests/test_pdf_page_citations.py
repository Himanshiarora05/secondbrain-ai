"""Offline checks for PDF page numbers: page-aware chunking and storage (no DB, no network, no LLM).

Run from backend/:  .venv/Scripts/python.exe tests/test_pdf_page_citations.py
"""
import asyncio
import io
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database, vector store or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-test-key")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"

import fitz
from fastapi import UploadFile

from app.api import upload
from app.services.pdf.pdf_service import PDFService
from app.services.rag.rag_service import RAGService


def sentences(tag, n, length=90):
    """n distinct sentences of about `length` characters, tagged so we can find them in chunks."""
    return " ".join(f"{tag} sentence {i} " + "x" * (length - len(f'{tag} sentence {i} ') - 1) + "." for i in range(n))


def make_pdf(pages):
    """Real PDF bytes with one text block per page ('' = blank page)."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(fitz.Rect(40, 40, 560, 800), text, fontsize=7)
    data = doc.tobytes()
    doc.close()
    return data


# ─── Chunker ───

def test_single_page_chunks_cite_that_page():
    chunks = RAGService.chunk_pages([sentences("A", 3)])
    assert len(chunks) == 1 and (chunks[0]["page_start"], chunks[0]["page_end"]) == (1, 1)


def test_chunk_running_over_a_page_break_spans_both_pages():
    # 6 x ~90 chars on page 1, then page 2: the chunk that fills to ~800 chars must cross the break.
    chunks = RAGService.chunk_pages([sentences("P1", 6), sentences("P2", 12)])
    spans = [(c["page_start"], c["page_end"]) for c in chunks]
    assert spans[0] == (1, 2), spans
    assert all(s in {(1, 2), (2, 2)} for s in spans), spans
    first = chunks[0]["text"]
    assert "P1 sentence 5" in first and "P2 sentence 0" in first


def test_overlap_carried_from_the_previous_page_is_counted():
    # Page 1 fills a whole chunk, so the next chunk starts with page-1 overlap before page-2 text.
    chunks = RAGService.chunk_pages([sentences("P1", 9), sentences("P2", 9)])
    second = chunks[1]
    assert second["text"].startswith("P1 sentence"), second["text"][:40]
    assert (second["page_start"], second["page_end"]) == (1, 2)
    assert (chunks[-1]["page_start"], chunks[-1]["page_end"]) == (2, 2)


def test_blank_pages_are_skipped_but_numbering_is_kept():
    chunks = RAGService.chunk_pages(["", sentences("P2", 2), "   \n  ", sentences("P4", 2)])
    assert [(c["page_start"], c["page_end"]) for c in chunks] == [(2, 4)]
    assert RAGService.chunk_pages(["", "  "]) == []


def test_many_pages_each_chunk_range_is_ordered_and_covers_its_text():
    pages = [sentences(f"P{n}", 4) for n in range(1, 21)]
    chunks = RAGService.chunk_pages(pages)
    for c in chunks:
        assert 1 <= c["page_start"] <= c["page_end"] <= 20
        cited = {int(tag[1:]) for tag in c["text"].split() if tag.startswith("P") and tag[1:].isdigit()}
        assert min(cited) == c["page_start"] and max(cited) == c["page_end"], (cited, c)
    assert chunks[0]["page_start"] == 1 and chunks[-1]["page_end"] == 20


def test_giant_sentence_slices_keep_their_page():
    chunks = RAGService.chunk_pages([sentences("P1", 2), "Long " + "y" * 2000 + "."])
    assert [(c["page_start"], c["page_end"]) for c in chunks][-3:] == [(2, 2)] * 3


def test_chunk_text_still_ignores_pages():
    """Other sources keep using chunk_text exactly as before (plain list of strings)."""
    text = sentences("A", 20)
    assert RAGService.chunk_text(text) == [c["text"] for c in RAGService.chunk_pages([text])]


# ─── Real PDF files ───

def test_extract_pages_from_a_real_pdf():
    path = Path(tempfile.mkdtemp()) / "three.pdf"
    path.write_bytes(make_pdf(["Alpha page one.", "", "Gamma page three."]))
    pages = PDFService.extract_pages(str(path))
    assert len(pages) == 3 and "Alpha" in pages[0] and not pages[1].strip() and "Gamma" in pages[2]
    assert PDFService.extract_text(str(path)) == "".join(pages)


def test_upload_pdf_stores_page_ranges():
    data = make_pdf([sentences("P1", 6), sentences("P2", 6), "", sentences("P4", 6)])
    tmp = Path(tempfile.mkdtemp(prefix="sb-test-uploads-"))
    with patch.object(upload, "UPLOAD_DIR", tmp), \
         patch.object(upload, "_store_document_and_chunks", return_value={"status": "stored"}) as store:
        result = asyncio.run(upload.upload_pdf(file=UploadFile(file=io.BytesIO(data), filename="notes.pdf"), db=MagicMock()))
    assert result == {"status": "stored"}
    kw = store.call_args.kwargs
    assert len(kw["chunks"]) == len(kw["chunk_pages"]) >= 2
    assert kw["chunk_pages"][0][0] == 1 and kw["chunk_pages"][-1][1] == 4
    assert all(3 not in range(s, e + 1) or s < 3 < e for s, e in kw["chunk_pages"]), "blank page 3 only inside a span"
    assert "P1 sentence 0" in kw["content"] and kw["source_type"] == "pdf"


def test_store_writes_pages_to_postgres_and_chroma():
    db = MagicMock()
    added = []
    db.add_all.side_effect = added.extend
    collection = MagicMock()
    with patch.object(upload, "get_embeddings", return_value=[[0.0], [0.0]]), \
         patch.object(upload, "get_collection", return_value=collection):
        upload._store_document_and_chunks(db=db, file_id="f", filename="notes.pdf", content="a b",
                                          chunks=["a", "b"], source_type="pdf", chunk_pages=[(1, 1), (1, 2)])
    assert [(c.page_start, c.page_end) for c in added] == [(1, 1), (1, 2)]
    metas = collection.add.call_args.kwargs["metadatas"]
    assert [(m["page_start"], m["page_end"]) for m in metas] == [(1, 1), (1, 2)]


def test_store_without_pages_leaves_them_empty():
    db = MagicMock()
    added = []
    db.add_all.side_effect = added.extend
    collection = MagicMock()
    with patch.object(upload, "get_embeddings", return_value=[[0.0]]), \
         patch.object(upload, "get_collection", return_value=collection):
        upload._store_document_and_chunks(db=db, file_id="f", filename="n.docx", content="a", chunks=["a"], source_type="docx")
    assert (added[0].page_start, added[0].page_end) == (None, None)
    assert "page_start" not in collection.add.call_args.kwargs["metadatas"][0]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
