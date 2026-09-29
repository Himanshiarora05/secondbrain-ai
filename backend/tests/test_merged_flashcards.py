"""Offline checks for merged flashcard decks: per-source shares, source-named citations and the
save rules (mocked LLM, in-memory SQLite, no network).

Run from backend/:  .venv/Scripts/python.exe tests/test_merged_flashcards.py
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database, vector store or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-test-key")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base
from app.models import Document, Chunk, Flashcard, MergedFlashcard, User
from app.routes import merged_sets as ms
from app.routes.merged_sets import CreateMergedSetRequest
from app.services.ai import flashcard_service as fs
from app.services.ai import merged_service as mg
from app.services.ai import summary_service as ss
from app.services.ai.merged_service import MergedSource

VIDEO = "https://www.youtube.com/watch?v=abcdefghijk"
PAGE = "https://example.org/cells"


class FakeLLM:
    """Returns as many cards as the prompt asks for, each citing the first label it was shown."""

    def __init__(self, fail=None):
        self.fail, self.calls = fail, []
        self.chat = MagicMock()
        self.chat.completions.create.side_effect = self._create

    def _create(self, **kw):
        user = kw["messages"][1]["content"]
        self.calls.append(user)
        if self.fail:
            raise self.fail
        n = int(re.search(r"Generate (\d+) exam flashcards", user).group(1))
        first = re.search(r"\[S(\d+)\]", user).group(1)
        topic = re.search(r"\[S\d+\] (\S+)", user).group(1)
        cards = [{"question": f"{topic} question {len(self.calls)}.{i}?", "answer": "An answer.", "source": f"S{first}"}
                 for i in range(n)]
        return MagicMock(choices=[MagicMock(finish_reason="stop", message=MagicMock(content=json.dumps(cards)))])


def test_shares_add_up_and_cover_every_source():
    assert mg.allocate_cards(10, [1000, 1000, 1000]) == [4, 3, 3]
    big = mg.allocate_cards(10, [50_000, 2_500, 300])
    assert sum(big) == 10 and min(big) >= 1 and big[0] == max(big), big
    assert mg.allocate_cards(10, [300, 0, 300]) == [5, 0, 5], "no text, no cards"
    assert mg.allocate_cards(2, [10, 30, 20]) == [0, 1, 1], "fewer cards than sources: the largest get one"
    assert mg.allocate_cards(0, [10, 10]) == [0, 0] and mg.allocate_cards(5, []) == []
    for count in range(1, 51):
        shares = mg.allocate_cards(count, [54_826, 2_576, 11_085, 320, 363, 217, 10_174, 4_000])
        assert sum(shares) == count, (count, shares)
        if count >= 8:
            assert min(shares) >= 1, (count, shares)


def test_card_citations_name_the_source():
    pdf = MergedSource(1, "Graph_PPT.pdf", "pdf", None, [], [])
    vid = MergedSource(2, "YouTube: abc", "youtube", VIDEO, [], [])
    web = MergedSource(3, "Cells", "website", PAGE, [], [])
    doc = MergedSource(4, "notes.docx", "docx", None, [], [])
    assert mg.merged_card_citation(pdf, "p. 12", None) == ("Graph_PPT.pdf · p. 12", None)
    assert mg.merged_card_citation(pdf, None, None) == ("Graph_PPT.pdf", None), "no usable label still names the source"
    assert mg.merged_card_citation(vid, "02:05", f"{VIDEO}&t=125s") == ("YouTube: abc · 02:05", f"{VIDEO}&t=125s")
    assert mg.merged_card_citation(web, "Cells", PAGE) == ("Cells", PAGE), "the page title isn't repeated"
    assert mg.merged_card_citation(doc, None, None) == ("notes.docx", None)


def test_deck_is_grouped_by_source_with_citations():
    sources = [
        MergedSource(1, "Graph_PPT.pdf", "pdf", None, ["Graphs are pairs. " * 40, "Degree counts. " * 40],
                     [("p. 1", None), ("pp. 2–3", None)], document_id=11),
        MergedSource(2, "YouTube: abc", "youtube", VIDEO, ["Video intro. " * 20], [("00:05", f"{VIDEO}&t=5s")], document_id=12),
        MergedSource(3, "Cells", "website", PAGE, ["Cells have nuclei. " * 20], [("Cells", PAGE)], document_id=13),
        MergedSource(4, "notes.docx", "docx", None, ["Word notes. " * 20], [None], document_id=14),
    ]
    llm = FakeLLM()
    with patch.object(fs, "client", llm):
        deck = mg.generate_merged_flashcards(sources, count=10)
    assert len(deck) == 10, len(deck)
    order = [c["document_id"] for c in deck]
    assert order == sorted(order), "grouped by source, in set order"
    shares = mg.allocate_cards(10, [sum(len(c.strip()) for c in s.chunks) for s in sources])
    assert [order.count(d) for d in (11, 12, 13, 14)] == shares, (order, shares)
    by_doc = {c["document_id"]: c for c in deck}
    assert by_doc[11]["source_label"] in ("Graph_PPT.pdf · p. 1", "Graph_PPT.pdf · pp. 2–3")
    assert (by_doc[12]["source_label"], by_doc[12]["source_url"]) == ("YouTube: abc · 00:05", f"{VIDEO}&t=5s")
    assert (by_doc[13]["source_label"], by_doc[13]["source_url"]) == ("Cells", PAGE)
    assert (by_doc[14]["source_label"], by_doc[14]["source_url"]) == ("notes.docx", None)
    for prompt in llm.calls:
        topics = set(re.findall(r"\[S\d+\] (\S+)", prompt))
        assert len(topics) == 1, f"a call mixed sources: {topics}"


# ─── Route (in-memory SQLite) ───

def fresh_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    # The signed-in user the routes are called for; add_doc gives it every document.
    owner = User(email="owner@example.com", password_hash="not-used")
    db.add(owner)
    db.commit()
    db.info["user"] = owner
    return db


def add_doc(db, name, source_type, chunks, pages=None, starts=None, url=None):
    doc = Document(user_id=db.info["user"].id, file_id=f"f-{name}", filename=name, content=" ".join(chunks), source_type=source_type, source_url=url)
    db.add(doc)
    db.flush()
    for i, text in enumerate(chunks):
        p = pages[i] if pages else (None, None)
        db.add(Chunk(document_id=doc.id, content=text, chroma_id=f"{doc.id}-{i}", page_start=p[0], page_end=p[1],
                     start_seconds=starts[i] if starts else None))
    db.commit()
    return doc.id


def library(db):
    pdf = add_doc(db, "Graph_PPT.pdf", "pdf", ["Graphs are pairs.", "Degree counts edges."], pages=[(1, 1), (2, 3)])
    ppt = add_doc(db, "quantum.pptx", "pptx", ["[Slide 1] Qubits.", "[Slide 2] Gates."])
    vid = add_doc(db, "YouTube: abcdefghijk", "youtube", ["Intro.", "Later."], starts=[5, 125], url=VIDEO)
    db.add(Flashcard(document_id=pdf, question="The PDF's own card?", answer="Yes."))
    db.commit()
    return pdf, ppt, vid


def post(db, set_id, count=6):
    try:
        return ms.create_merged_flashcards(set_id, count=count, db=db, user=db.info["user"])
    except HTTPException as e:
        return e


def test_route_generates_replaces_and_keeps_on_failure():
    db = fresh_db()
    pdf, ppt, vid = library(db)
    set_id = ms.create_merged_set(CreateMergedSetRequest(document_ids=[pdf, ppt, vid]), db=db, user=db.info["user"])["merged_set"]["id"]
    assert ms.get_merged_flashcards(set_id, db=db, user=db.info["user"]) == {"set_id": set_id, "flashcards": [], "stale": False}

    with patch.object(fs, "client", FakeLLM()):
        first = post(db, set_id)
    cards = first["flashcards"]
    assert len(cards) == 6 and {c["document_id"] for c in cards} == {pdf, ppt, vid}, cards
    labels = {c["source_label"] for c in cards}
    assert "Graph_PPT.pdf · p. 1" in labels and "quantum.pptx · Slide 1" in labels, labels
    assert any(c["source_url"] == f"{VIDEO}&t=5s" for c in cards)
    assert ms.get_merged_set(set_id, db=db, user=db.info["user"])["flashcard_count"] == 6

    with patch.object(fs, "client", FakeLLM(fail=RuntimeError("boom"))), patch.object(ss, "logger"):
        res = post(db, set_id)
    assert isinstance(res, HTTPException) and res.status_code == 502, res
    assert res.detail.endswith("Your existing flashcards were not changed."), res.detail
    assert [c.id for c in db.query(MergedFlashcard).order_by(MergedFlashcard.id)] == [c["id"] for c in cards]

    with patch.object(fs, "client", FakeLLM()):
        second = post(db, set_id, count=3)
    assert len(second["flashcards"]) == 3 and db.query(MergedFlashcard).count() == 3, "the old deck is replaced"
    assert db.query(Flashcard).one().question == "The PDF's own card?", "the document's own deck is untouched"


def test_deleted_member_marks_the_deck_stale():
    db = fresh_db()
    pdf, ppt, vid = library(db)
    set_id = ms.create_merged_set(CreateMergedSetRequest(document_ids=[pdf, ppt, vid]), db=db, user=db.info["user"])["merged_set"]["id"]
    with patch.object(fs, "client", FakeLLM()):
        post(db, set_id)
    db.delete(db.get(Document, ppt))
    db.commit()
    db.expire_all()
    deck = ms.get_merged_flashcards(set_id, db=db, user=db.info["user"])
    assert deck["stale"] is True and len(deck["flashcards"]) == 6, "cards stay, unlinked"
    assert any(c["document_id"] is None and c["source_label"].startswith("quantum.pptx") for c in deck["flashcards"])
    with patch.object(fs, "client", FakeLLM()):
        fresh = post(db, set_id)
    assert fresh["stale"] is False and {c["document_id"] for c in fresh["flashcards"]} == {pdf, vid}
    db.delete(db.get(Document, vid))
    db.commit()
    res = post(db, set_id)
    assert isinstance(res, HTTPException) and res.status_code == 400 and "fewer than 2" in res.detail


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
