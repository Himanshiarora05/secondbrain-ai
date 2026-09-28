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


# ─── Stage 2: citations and flashcards ───

def test_format_pages():
    from app.services.ai.summary_service import format_pages
    assert format_pages(12, 12) == "p. 12"
    assert format_pages(12, None) == "p. 12"
    assert format_pages(12, 13) == "pp. 12–13"
    assert format_pages(None, None) is None


def test_pdf_chunk_citations_come_from_stored_pages():
    from app.services.ai.flashcard_service import build_chunk_citations
    cites = build_chunk_citations("pdf", None, "notes.pdf", [("a", None), ("b", None), ("c", None)],
                                  pages=[(1, 1), (1, 2), (None, None)])
    assert cites == [("p. 1", None), ("pp. 1–2", None), None]
    # A PDF uploaded before page tracking has no pages at all.
    assert build_chunk_citations("pdf", None, "old.pdf", [("a", None)]) == [None]
    assert build_chunk_citations("pdf", None, "old.pdf", [("a", None)], pages=[(None, None)]) == [None]


def test_pdf_flashcards_cite_pages_through_the_route():
    import json
    from app.routes import study
    from app.services.ai import flashcard_service as fs
    from app.models.chunk import Chunk
    from app.models.document import Document
    from app.models.flashcard import Flashcard

    doc = MagicMock(id=9, content="text", source_type="pdf", source_url=None)
    doc.filename = "notes.pdf"
    rows = [MagicMock(content="Cells are units of life.", start_seconds=None, page_start=3, page_end=3),
            MagicMock(content="ATP is made in mitochondria.", start_seconds=None, page_start=3, page_end=4)]
    saved = []

    def query(model):
        q = MagicMock()
        if model is Document:
            q.filter.return_value.first.return_value = doc
        elif model is Chunk:
            q.filter.return_value.order_by.return_value.all.return_value = rows
        elif model is Flashcard:
            q.filter.return_value.order_by.return_value.all.side_effect = lambda: [
                MagicMock(id=i, question=c.question, answer=c.answer, source_label=c.source_label, source_url=c.source_url)
                for i, c in enumerate(saved, start=1)]
        return q

    db = MagicMock()
    db.query.side_effect = query
    db.add_all.side_effect = saved.extend
    reply = MagicMock()
    reply.choices = [MagicMock(message=MagicMock(content=json.dumps([
        {"question": "What makes ATP?", "answer": "Mitochondria.", "source": "S1"},
        {"question": "What are cells?", "answer": "Units of life.", "source": "S0"},
    ])))]
    client = MagicMock()
    client.chat.completions.create.return_value = reply
    with patch.object(fs, "client", client), patch.object(fs, "CARDS_PER_CALL", 10):
        result = study.create_flashcards(9, count=2, db=db)
    labels = {c["question"]: (c["source_label"], c["source_url"]) for c in result["flashcards"]}
    assert labels == {"What makes ATP?": ("pp. 3–4", None), "What are cells?": ("p. 3", None)}, labels


# ─── Stage 3: summaries ───

def test_replace_labels_with_pages_and_slides():
    from app.services.ai.summary_service import replace_labels
    cites = [("p. 1", None), ("pp. 1–2", None), ("p. 1", None), None]
    out = replace_labels("- A [S0]\n- B [S1][S0]\n- C [S0, S2]\n- D [S3]\n- E [S9]\n- F", cites)
    assert out.splitlines() == [
        "- A (p. 1)",
        "- B (pp. 1–2; p. 1)",
        "- C (p. 1)",          # two chunks on the same page: cited once
        "- D",                 # chunk without a citation: label dropped
        "- E",                 # invented label: dropped
        "- F",
    ], out
    assert replace_labels("- Qubits [S0]", [("Slide 4", None)]) == "- Qubits (Slide 4)"


def test_links_and_plain_citations_can_mix():
    from app.services.ai.summary_service import replace_labels
    out = replace_labels("- X [S0][S1]", [("02:05", "https://youtu.be/x?t=125"), ("p. 3", None)])
    assert out == "- X [02:05](https://youtu.be/x?t=125) (p. 3)", out


def _fake_summary_client(reply):
    prompts = []

    def create(**kwargs):
        prompts.append(kwargs["messages"][-1]["content"])
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content=reply(prompts[-1])))]
        return resp

    client = MagicMock()
    client.chat.completions.create.side_effect = create
    return client, prompts


def test_cited_summary_labels_chunks_and_cites_pages():
    from app.services.ai import summary_service as ss
    client, prompts = _fake_summary_client(lambda _: "## Cells\n- Cells are units of life [S0]\n- ATP from mitochondria [S1] [S7]")
    with patch.object(ss, "client", client):
        out = ss.generate_cited_summary(["Cells are units.", "Mitochondria make ATP."], [("p. 3", None), ("pp. 3–4", None)])
    assert "[S0] Cells are units." in prompts[0] and "[S1] Mitochondria make ATP." in prompts[0]
    assert out == "## Cells\n- Cells are units of life (p. 3)\n- ATP from mitochondria (pp. 3–4)", out


def test_long_pdf_summary_keeps_global_labels_through_map_reduce():
    from app.services.ai import summary_service as ss
    chunks = [f"Topic {i}. " + "x" * 780 for i in range(14)]
    cites = [(f"p. {i + 1}", None) for i in range(14)]

    def reply(prompt):
        if prompt.startswith("Extract key concepts"):
            first = prompt.split("[S", 1)[1].split("]", 1)[0]
            return f"- point [S{first}]"
        return "## Summary\n- early [S0]\n- late [S13]"

    client, prompts = _fake_summary_client(reply)
    with patch.object(ss, "client", client):
        out = ss.generate_cited_summary(chunks, cites)
    assert len(prompts) > 2
    assert out == "## Summary\n- early (p. 1)\n- late (p. 14)", out


def _summary_db(doc, rows):
    from app.models.chunk import Chunk
    from app.models.document import Document
    from app.models.summary import Summary

    def query(model):
        q = MagicMock()
        if model is Document:
            q.filter.return_value.first.return_value = doc
        elif model is Summary:
            q.filter.return_value.first.return_value = None
        elif model is Chunk:
            q.filter.return_value.order_by.return_value.all.return_value = rows
        return q

    db = MagicMock()
    db.query.side_effect = query
    return db


def _doc(source_type):
    doc = MagicMock(id=4, content="Full document text.", source_type=source_type, source_url=None)
    doc.filename = f"notes.{source_type}"
    return doc


def test_summary_route_picks_cited_or_plain_summary():
    from app.routes import study
    from app.services.ai.summary_service import replace_labels
    pdf_rows = [MagicMock(content="Cells.", start_seconds=None, page_start=2, page_end=2)]
    old_pdf_rows = [MagicMock(content="Cells.", start_seconds=None, page_start=None, page_end=None)]
    deck_rows = [MagicMock(content="[Slide 4: Qubits]\nA qubit holds 0 and 1.", start_seconds=None, page_start=None, page_end=None)]
    cases = [
        ("pdf", pdf_rows, "cited", "- Point (p. 2)"),
        ("pdf", old_pdf_rows, "plain", "- Plain summary"),   # uploaded before page tracking
        ("pptx", deck_rows, "cited", "- Point (Slide 4)"),
        ("docx", pdf_rows, "plain", "- Plain summary"),       # Word: no location, never cited
    ]
    for source_type, rows, kind, expected in cases:
        with patch.object(study, "generate_summary", return_value="- Plain summary") as plain, \
             patch.object(study, "generate_cited_summary",
                          side_effect=lambda chunks, cites: replace_labels("- Point [S0]", cites)) as cited:
            result = study.create_or_regenerate_summary(4, regenerate=False, db=_summary_db(_doc(source_type), rows))
        assert result["summary"] == expected, (source_type, kind, result["summary"])
        assert (cited.called, plain.called) == ((True, False) if kind == "cited" else (False, True)), (source_type, kind)


# ─── Stage 4: search ───

def test_search_matches_carry_a_location():
    from app.services import search_service
    from app.routes import search as search_route
    collection = MagicMock()
    collection.query.return_value = {
        "ids": [["1-0", "2-0", "3-0", "4-0"]],
        "documents": [["pdf text", "old pdf text", "video text", "web text"]],
        "metadatas": [[
            {"filename": "notes.pdf", "source_type": "pdf", "page_start": 3, "page_end": 4},
            {"filename": "old.pdf", "source_type": "pdf"},                      # uploaded before page tracking
            {"filename": "YouTube: abcdefghijk", "source_type": "youtube",
             "source_url": "https://www.youtube.com/watch?v=abcdefghijk", "start_seconds": 46},
            {"filename": "Page", "source_type": "website", "source_url": "https://example.com/a"},
        ]],
        "distances": [[0.1, 0.2, 0.3, 0.4]],
    }
    with patch.object(search_service, "get_collection", return_value=collection), \
         patch.object(search_service, "get_embedding", return_value=[0.0]):
        results = search_service.search_similar_chunks("q")
        assert [r[6] for r in results] == ["pp. 3–4", None, "00:46", None]
        with patch.object(search_route, "generate_answer", return_value="An answer."):
            response = search_route.search(query="q")
    assert [m["location"] for m in response["top_matches"]] == ["pp. 3–4", None, "00:46"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
