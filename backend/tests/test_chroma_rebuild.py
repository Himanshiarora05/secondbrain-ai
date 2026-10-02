"""Offline checks for rebuilding an empty Chroma collection from the chunks in Postgres.

Documents are stored through the real upload helper (`_store_document_and_chunks`)
into an in-memory SQLite database and a throwaway Chroma, with a fake embedder;
the collection is then emptied and rebuilt, and must come back with the same ids,
texts and metadata. No Postgres, network or model download.

Run from backend/:  .venv/Scripts/python.exe tests/test_chroma_rebuild.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database, vector store or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import upload
from app.database import chroma_rebuild
from app.database.chroma import get_collection
from app.database.db import Base
from app.models import Chunk, Document, User

col = get_collection()


def fake_embed(texts):
    return [[float(len(t)), 1.0, 0.5] for t in texts]


def fresh_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    owner = User(email="owner@example.com", password_hash="not-used")
    db.add(owner)
    db.commit()
    return db, owner.id


def clear_collection():
    ids = col.get()["ids"]
    if ids:
        col.delete(ids=ids)


def snapshot():
    got = col.get(include=["documents", "metadatas"])
    return {i: (d, m) for i, d, m in zip(got["ids"], got["documents"], got["metadatas"])}


def store_sample_documents(db, user_id):
    with patch.object(upload, "get_embeddings", fake_embed):
        upload._store_document_and_chunks(
            db, "f-pdf", "notes.pdf", "a b c", ["Page one text.", "Pages one and two.", "Page three."],
            source_type="pdf", chunk_pages=[(1, 1), (1, 2), (3, 3)], user_id=user_id)
        upload._store_document_and_chunks(
            db, "f-yt", "Lecture", "x y", ["Intro.", "Main part."], source_type="youtube",
            source_url="https://www.youtube.com/watch?v=abc", chunk_start_seconds=[0, 125], user_id=user_id)
        upload._store_document_and_chunks(
            db, "f-web", "A page", "w", ["Web text."], source_type="website",
            source_url="https://example.com/a", user_id=user_id)
        upload._store_document_and_chunks(
            db, "f-docx", "essay.docx", "d", ["Word text."], source_type="docx", user_id=user_id)
        # From before accounts: no user_id on the document, so none in the metadata either.
        upload._store_document_and_chunks(db, "f-old", "old.pptx", "o", ["[Slide 1] Old."], source_type="pptx")


def test_rebuild_restores_what_upload_stored():
    clear_collection()
    db, user_id = fresh_db()
    store_sample_documents(db, user_id)
    stored = snapshot()
    assert len(stored) == 8

    clear_collection()
    assert col.count() == 0
    assert chroma_rebuild.rebuild_if_empty(db=db, collection=col, embed=fake_embed) == 8
    rebuilt = snapshot()
    assert rebuilt == stored, f"rebuilt vectors differ:\n{rebuilt}\n!=\n{stored}"

    # Spot checks, so a broken upload helper can't make both sides wrong the same way.
    pdf_doc = db.query(Document).filter(Document.file_id == "f-pdf").one()
    _, meta = rebuilt[f"{pdf_doc.id}-1"]
    assert meta == {"document_id": pdf_doc.id, "filename": "notes.pdf", "chunk_index": 1,
                    "source_type": "pdf", "user_id": user_id, "page_start": 1, "page_end": 2}
    yt_doc = db.query(Document).filter(Document.file_id == "f-yt").one()
    _, meta = rebuilt[f"{yt_doc.id}-1"]
    assert meta["start_seconds"] == 125 and meta["source_url"].endswith("v=abc") and meta["user_id"] == user_id
    old_doc = db.query(Document).filter(Document.file_id == "f-old").one()
    assert "user_id" not in rebuilt[f"{old_doc.id}-0"][1]

    # Search filters on user_id, so the rebuilt vectors must answer that query.
    hits = col.query(query_embeddings=[fake_embed(["Page one text."])[0]], n_results=10,
                     where={"user_id": user_id})
    assert len(hits["ids"][0]) == 7


def test_rebuild_does_nothing_when_collection_has_vectors():
    clear_collection()
    db, user_id = fresh_db()
    store_sample_documents(db, user_id)
    calls = []
    assert chroma_rebuild.rebuild_if_empty(db=db, collection=col, embed=lambda t: calls.append(t)) == 0
    assert calls == [], "no embedding when the collection already has vectors"


def test_rebuild_batches_and_falls_back_for_missing_chroma_id():
    clear_collection()
    db, user_id = fresh_db()
    doc = Document(file_id="f-big", filename="big.pdf", content="", source_type="pdf", user_id=user_id)
    db.add(doc)
    db.flush()
    db.add_all([Chunk(document_id=doc.id, content=f"chunk {i}", chroma_id=None if i == 3 else f"{doc.id}-{i}")
                for i in range(7)])
    db.commit()
    batches = []

    def counting_embed(texts):
        batches.append(len(texts))
        return fake_embed(texts)

    with patch.object(chroma_rebuild, "BATCH_SIZE", 3):
        assert chroma_rebuild.rebuild_if_empty(db=db, collection=col, embed=counting_embed) == 7
    assert batches == [3, 3, 1]
    rebuilt = snapshot()
    assert sorted(rebuilt) == sorted(f"{doc.id}-{i}" for i in range(7))
    assert rebuilt[f"{doc.id}-3"] == ("chunk 3", {"document_id": doc.id, "filename": "big.pdf", "chunk_index": 3,
                                                   "source_type": "pdf", "user_id": user_id})


def test_rebuild_of_empty_database_adds_nothing():
    clear_collection()
    db, _ = fresh_db()
    assert chroma_rebuild.rebuild_if_empty(db=db, collection=col, embed=fake_embed) == 0
    assert col.count() == 0


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
