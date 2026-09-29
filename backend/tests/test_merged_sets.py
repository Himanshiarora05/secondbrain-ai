"""Offline checks for merged sets: create / list / rename / delete, and how they react to deleted documents.

Runs the route functions against an in-memory SQLite database (foreign keys on),
so cascades and ON DELETE SET NULL really happen. No Postgres, Chroma or network.

Run from backend/:  .venv/Scripts/python.exe tests/test_merged_sets.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database, vector store or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base
from app.models import Document, Chunk, Summary, Flashcard, MergedSet, MergedSetDocument, MergedSummary, MergedFlashcard
from app.routes import merged_sets as ms
from app.routes.merged_sets import CreateMergedSetRequest, RenameMergedSetRequest


def fresh_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def add_doc(db, name, chars=1000, source_type="pdf"):
    doc = Document(file_id=f"f-{name}", filename=name, content="x" * chars, source_type=source_type)
    db.add(doc)
    db.commit()
    return doc.id


def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except HTTPException as e:
        return e


def create(db, ids, name=None):
    return call(ms.create_merged_set, CreateMergedSetRequest(document_ids=ids, name=name), db=db)


def test_create_names_and_orders_the_set():
    db = fresh_db()
    a, b, c = add_doc(db, "Graph_PPT.pdf"), add_doc(db, "quantum.pptx"), add_doc(db, "YouTube: abc", source_type="youtube")
    res = create(db, [b, a])
    assert res["created"] is True
    s = res["merged_set"]
    assert s["name"] == "quantum.pptx + Graph_PPT.pdf", s["name"]
    assert [d["id"] for d in s["documents"]] == [b, a], "selection order is kept"
    assert (s["has_summary"], s["flashcard_count"], s["summary_stale"], s["flashcards_stale"]) == (False, 0, False, False)
    three = create(db, [a, b, c])["merged_set"]
    assert three["name"] == "Graph_PPT.pdf + quantum.pptx + 1 more", three["name"]
    assert three["documents"][2]["source_type"] == "youtube"


def test_custom_name_is_tidied_and_checked():
    db = fresh_db()
    a, b = add_doc(db, "a.pdf"), add_doc(db, "b.pdf")
    assert create(db, [a, b], name="  Graph   revision ")["merged_set"]["name"] == "Graph revision"
    c = add_doc(db, "c.pdf")
    for bad in ("   ", "x" * 256):
        res = create(db, [a, c], name=bad)
        assert isinstance(res, HTTPException) and res.status_code == 400, res


def test_selection_rules():
    db = fresh_db()
    ids = [add_doc(db, f"d{i}.pdf", chars=100) for i in range(9)]
    for bad, status, text in [
        ([ids[0]], 400, "at least 2"),
        ([ids[0], ids[0]], 400, "at least 2"),       # repeats are dropped first
        (ids, 400, "at most 8"),
        ([ids[0], 999], 404, "999"),
    ]:
        res = create(db, bad)
        assert isinstance(res, HTTPException) and res.status_code == status and text in res.detail, (bad, res)
    assert create(db, ids[:8])["created"] is True
    assert db.query(MergedSetDocument).count() == 8


def test_character_limit():
    db = fresh_db()
    a, b = add_doc(db, "big.pdf", chars=60_000), add_doc(db, "other.pdf", chars=20_000)
    assert create(db, [a, b])["created"] is True, "exactly 80,000 is allowed"
    c = add_doc(db, "one-more.pdf", chars=1)
    res = create(db, [a, b, c])
    assert isinstance(res, HTTPException) and res.status_code == 400, res
    assert "80,001 characters" in res.detail and "at most 80,000" in res.detail, res.detail


def test_same_documents_reopen_the_existing_set():
    db = fresh_db()
    a, b, c = add_doc(db, "a.pdf"), add_doc(db, "b.pdf"), add_doc(db, "c.pdf")
    first = create(db, [a, b])["merged_set"]
    again = create(db, [b, a, a])
    assert again["created"] is False and again["merged_set"]["id"] == first["id"]
    assert create(db, [a, b, c])["created"] is True, "a superset is a different set"
    assert create(db, [a, c])["created"] is True, "an overlapping set is a different set"
    assert db.query(MergedSet).count() == 3


def test_list_get_rename():
    db = fresh_db()
    a, b, c = add_doc(db, "a.pdf"), add_doc(db, "b.pdf"), add_doc(db, "c.pdf")
    older = create(db, [a, b])["merged_set"]["id"]
    newer = create(db, [a, c])["merged_set"]["id"]
    assert [s["id"] for s in ms.list_merged_sets(db=db)] == [newer, older], "newest first"
    assert ms.get_merged_set(older, db=db)["name"] == "a.pdf + b.pdf"
    assert ms.rename_merged_set(older, RenameMergedSetRequest(name=" Week 3 "), db=db)["name"] == "Week 3"
    assert call(ms.rename_merged_set, older, RenameMergedSetRequest(name=" "), db=db).status_code == 400
    assert call(ms.get_merged_set, 999, db=db).status_code == 404
    assert call(ms.rename_merged_set, 999, RenameMergedSetRequest(name="x"), db=db).status_code == 404


def test_deleting_a_set_leaves_documents_and_their_study_material_alone():
    db = fresh_db()
    a, b = add_doc(db, "a.pdf"), add_doc(db, "b.pdf")
    db.add_all([Summary(document_id=a, content="own summary"), Flashcard(document_id=a, question="Q", answer="A")])
    set_id = create(db, [a, b])["merged_set"]["id"]
    db.add_all([MergedSummary(set_id=set_id, content="merged", document_ids=json.dumps([a, b])),
                MergedFlashcard(set_id=set_id, document_id=a, question="MQ", answer="MA")])
    db.commit()
    res = ms.delete_merged_set(set_id, db=db)
    assert "not changed" in res["message"]
    assert db.query(MergedSet).count() == 0
    assert db.query(MergedSetDocument).count() == db.query(MergedSummary).count() == db.query(MergedFlashcard).count() == 0
    assert db.query(Document).count() == 2
    assert db.query(Summary).one().content == "own summary" and db.query(Flashcard).count() == 1
    assert call(ms.delete_merged_set, set_id, db=db).status_code == 404


def test_deleted_document_leaves_the_set_readable_but_stale():
    db = fresh_db()
    a, b, c = add_doc(db, "a.pdf"), add_doc(db, "b.pdf"), add_doc(db, "c.pdf")
    set_id = create(db, [a, b, c])["merged_set"]["id"]
    db.add_all([MergedSummary(set_id=set_id, content="merged (1: p. 1)", document_ids=json.dumps([a, b, c])),
                MergedFlashcard(set_id=set_id, document_id=b, question="Q", answer="A", source_label="b.pdf · p. 2"),
                MergedFlashcard(set_id=set_id, document_id=a, question="Q2", answer="A2")])
    db.commit()
    db.delete(db.get(Document, b))
    db.commit()
    db.expire_all()
    s = ms.get_merged_set(set_id, db=db)
    assert [d["id"] for d in s["documents"]] == [a, c], "membership went with the document"
    assert s["has_summary"] and s["summary_stale"] and s["flashcards_stale"] and s["flashcard_count"] == 2
    card = db.query(MergedFlashcard).filter(MergedFlashcard.question == "Q").one()
    assert card.document_id is None and card.source_label == "b.pdf · p. 2", "the card keeps its citation text"
    assert db.query(MergedSummary).one().content == "merged (1: p. 1)"
    # The remaining two documents now match a request for [a, c].
    assert create(db, [c, a])["merged_set"]["id"] == set_id


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
