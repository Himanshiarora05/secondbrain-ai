"""Offline checks for search vectors in Postgres (pgvector): storing them at upload,
searching only the signed-in user's chunks, and keeping them in step with rename,
delete and re-indexing; init_db's schema; and scripts/migrate_chroma_to_pgvector.py.

Runs on a throwaway Postgres with pgvector (tests/pg_test_db.py). Embeddings are
fake, chosen so the nearest-neighbour order is known; no model, network or AI.

Run from backend/:  .venv/Scripts/python.exe tests/test_pgvector_store.py
"""
import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database or model hub.
os.environ["DATABASE_URL"] = "postgresql://offline:offline@127.0.0.1:1/offline"
os.environ["HF_HUB_OFFLINE"] = "1"

from fastapi import HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

import app.database.db as dbmod
from app.api import upload
from app.models import Chunk, ChunkEmbedding, Document, User
from app.routes import documents
from app.services import search_service
from scripts import migrate_chroma_to_pgvector as migrate
from scripts import reindex_pdf_pages as reindex
from tests.pg_test_db import axis_vector, fake_embedding, pg_engine

# Each text that matters gets its own direction, so "nearest" is predictable:
# a query on axis i is closest to chunks on axis i, then to ones that lean on it.
AXES = {"cells": 0, "genes": 1, "history": 2, "music": 3}


def embed_texts(texts):
    out = []
    for t in texts:
        topic = next((k for k in AXES if k in t.lower()), None)
        out.append(axis_vector(AXES[topic], 0.9, other=10) if topic else fake_embedding(t))
    return out


def fresh():
    engine = pg_engine()
    Local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Local()
    alice, bob = User(email="alice@example.com", password_hash="x"), User(email="bob@example.com", password_hash="x")
    db.add_all([alice, bob])
    db.commit()
    return db, Local, alice, bob


def store(db, user, name, chunks, **kw):
    with patch.object(upload, "get_embeddings", side_effect=embed_texts):
        return upload._store_document_and_chunks(db, f"f-{name}", name, " ".join(chunks), chunks, user_id=user.id, **kw)["document_id"]


def search(db, user, topic, top_k=5):
    with patch.object(search_service, "get_embedding", return_value=axis_vector(AXES[topic])):
        return search_service.search_similar_chunks(db, topic, user.id, top_k=top_k)


def vector_count(db, doc_id=None):
    q = db.query(ChunkEmbedding).join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
    return (q.filter(Chunk.document_id == doc_id) if doc_id is not None else q).count()


# ─── upload and search ───

def test_upload_stores_one_vector_per_chunk():
    db, _, alice, _ = fresh()
    doc_id = store(db, alice, "bio.pdf", ["About cells.", "About genes.", "Misc text."],
                   source_type="pdf", chunk_pages=[(1, 1), (1, 2), (3, 3)])
    chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).order_by(Chunk.id).all()
    assert [(c.page_start, c.page_end) for c in chunks] == [(1, 1), (1, 2), (3, 3)]
    assert vector_count(db, doc_id) == 3
    stored = db.get(ChunkEmbedding, chunks[0].id).embedding
    assert len(stored) == 384 and abs(float(stored[0]) - 0.9) < 1e-6


def test_search_finds_nearest_first_with_locations():
    db, _, alice, _ = fresh()
    store(db, alice, "bio.pdf", ["About cells.", "About genes."], source_type="pdf", chunk_pages=[(4, 5), (6, 6)])
    store(db, alice, "Lecture", ["Cells on video.", "History on video."], source_type="youtube",
          source_url="https://www.youtube.com/watch?v=abcdefghijk", chunk_start_seconds=[46, 125])
    store(db, alice, "A page", ["Music page."], source_type="website", source_url="https://example.com/m")

    results = search(db, alice, "cells")
    assert [r[1] for r in results[:2]] == ["About cells.", "Cells on video."] or \
           [r[1] for r in results[:2]] == ["Cells on video.", "About cells."], results
    by_text = {r[1]: r for r in results}
    score, _, name, yt_url, source_type, source_url, location = by_text["About cells."]
    assert (name, source_type, location, yt_url) == ("bio.pdf", "pdf", "pp. 4–5", None)
    assert abs(score - 0.9) < 1e-4, score  # cosine similarity of the two axis vectors
    video = by_text["Cells on video."]
    assert video[3] == "https://www.youtube.com/watch?v=abcdefghijk&t=46s" and video[6] == "00:46"
    assert results[0][0] >= results[-1][0], "most similar first"

    top = search(db, alice, "music", top_k=1)
    assert [(r[1], r[2], r[4], r[5], r[6]) for r in top] == [("Music page.", "A page", "website", "https://example.com/m", None)]


def test_search_only_sees_the_users_documents():
    db, _, alice, bob = fresh()
    store(db, alice, "alice.docx", ["Alice on history."], source_type="docx")
    store(db, bob, "bob.docx", ["Bob on history.", "Bob on music."], source_type="docx")
    assert [r[1] for r in search(db, alice, "history")] == ["Alice on history."]
    assert {r[1] for r in search(db, bob, "history")} == {"Bob on history.", "Bob on music."}
    stranger = SimpleNamespace(id=999)
    assert search(db, stranger, "history") == []


def test_documents_without_an_owner_are_not_searched():
    db, _, alice, _ = fresh()
    doc_id = store(db, alice, "old.pdf", ["Old cells notes."], source_type="pdf")
    db.query(Document).filter(Document.id == doc_id).update({"user_id": None})
    db.commit()
    assert search(db, alice, "cells") == []


def test_failed_upload_stores_nothing():
    db, _, alice, _ = fresh()
    # Vectors of the wrong size: the insert fails.
    with patch.object(upload, "get_embeddings", return_value=[[1.0, 2.0]]), patch.object(upload, "logger"):
        try:
            upload._store_document_and_chunks(db, "f-bad", "bad.pdf", "x", ["x"], user_id=alice.id)
            raise AssertionError("expected a 500")
        except HTTPException as e:
            assert e.status_code == 500
    assert db.query(Document).count() == 0 and db.query(Chunk).count() == 0 and vector_count(db) == 0


# ─── rename and delete ───

def test_rename_shows_in_search():
    db, _, alice, _ = fresh()
    doc_id = store(db, alice, "old name.pdf", ["Genes text."], source_type="pdf")
    documents.rename_document(doc_id, documents.RenameRequest(filename="New name.pdf"), db=db, user=alice)
    assert search(db, alice, "genes")[0][2] == "New name.pdf"


def test_delete_removes_the_documents_vectors_only():
    db, _, alice, _ = fresh()
    gone = store(db, alice, "gone.pdf", ["Cells a.", "Cells b."], source_type="pdf")
    kept = store(db, alice, "kept.pdf", ["Cells c."], source_type="pdf")
    with patch.object(documents, "UPLOAD_DIR", Path(os.environ.get("TEMP", "."))):
        documents.delete_document(gone, db=db, user=alice)
    db.expire_all()
    assert vector_count(db, gone) == 0 and vector_count(db) == 1 and vector_count(db, kept) == 1
    orphans = db.execute(text("SELECT count(*) FROM chunk_embeddings e LEFT JOIN chunks c ON c.id = e.chunk_id "
                              "WHERE c.id IS NULL")).scalar()
    assert orphans == 0
    assert [r[2] for r in search(db, alice, "cells")] == ["kept.pdf"]


# ─── re-indexing ───

NEW = [{"text": "Genes on page one.", "page_start": 1, "page_end": 1},
       {"text": "Genes across pages.", "page_start": 1, "page_end": 2}]


def test_reindex_replaces_chunks_and_vectors():
    db, _, alice, _ = fresh()
    doc_id = store(db, alice, "old.pdf", ["Old genes 1.", "Old genes 2.", "Old genes 3."], source_type="pdf")
    doc = db.get(Document, doc_id)
    reindex.apply_document(db, doc, NEW, embed=embed_texts)
    db.expire_all()
    assert vector_count(db, doc_id) == 2 and vector_count(db) == 2, "old vectors went with their chunks"
    results = search(db, alice, "genes")
    assert sorted((r[1], r[6]) for r in results) == [("Genes across pages.", "pp. 1–2"), ("Genes on page one.", "p. 1")]


def test_reindex_failure_keeps_the_old_chunks_and_vectors():
    db, Local, alice, _ = fresh()
    doc_id = store(db, alice, "old.pdf", ["Old genes 1.", "Old genes 2."], source_type="pdf")
    failed = False
    try:  # vectors of the wrong size: the insert fails after the old chunks were deleted
        reindex.apply_document(db, db.get(Document, doc_id), NEW, embed=lambda texts: [[1.0]] * len(texts))
    except Exception:
        failed = True
    assert failed, "the failure should be reported"
    check = Local()
    assert check.query(Chunk).filter(Chunk.document_id == doc_id).count() == 2 and vector_count(check, doc_id) == 2


# ─── init_db ───

def test_init_db_creates_extension_table_and_index():
    engine = pg_engine(create_tables=False)
    with patch.object(dbmod, "engine", engine):
        dbmod.init_db()
        dbmod.init_db()  # running again (every startup) is harmless
    insp = inspect(engine)
    assert "chunk_embeddings" in insp.get_table_names()
    col = {c["name"]: c for c in insp.get_columns("chunk_embeddings")}["embedding"]
    assert "VECTOR(384)" in str(col["type"]).upper(), col["type"]
    fks = insp.get_foreign_keys("chunk_embeddings")
    assert fks and fks[0]["referred_table"] == "chunks" and fks[0]["options"].get("ondelete") == "CASCADE", fks
    assert "ix_chunks_document_id" in {i["name"] for i in insp.get_indexes("chunks")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")).scalar() == 1


def test_init_db_explains_a_missing_pgvector():
    class ServerWithoutPgvector:
        def begin(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, *args, **kwargs):
            raise RuntimeError('extension "vector" is not available')

    with patch.object(dbmod, "engine", ServerWithoutPgvector()):
        try:
            dbmod.init_db()
            raise AssertionError("expected a RuntimeError")
        except RuntimeError as e:
            assert "pgvector" in str(e) and "Neon" in str(e), e


# ─── scripts/migrate_chroma_to_pgvector.py ───

class FakeChroma:
    """Enough of a Chroma collection for the script: count() and paged get()."""

    def __init__(self, items):
        self.items = items  # [(id, embedding, metadata)]

    def count(self):
        return len(self.items)

    def get(self, include, limit, offset):
        page = self.items[offset:offset + limit]
        return {"ids": [i for i, _, _ in page], "embeddings": [e for _, e, _ in page],
                "metadatas": [m for _, _, m in page]}


def legacy_document(db, user, name, n, topic):
    """A document stored the old way: chunks with chroma_id, no vectors in Postgres."""
    doc = Document(file_id=f"f-{name}", filename=name, content="x", source_type="pdf", user_id=user.id)
    db.add(doc)
    db.flush()
    chunks = [Chunk(document_id=doc.id, content=f"{topic} {i}", chroma_id=f"{doc.id}-{i}") for i in range(n)]
    db.add_all(chunks)
    db.commit()
    return doc, chunks


def run_script(db, Local, engine, collection, *args):
    # End the test's own transaction first: with --apply the script runs init_db,
    # whose ALTER TABLEs wait for every open transaction on those tables.
    if db is not None:
        db.commit()
    out = io.StringIO()
    with patch.object(migrate, "open_collection", return_value=collection), \
         patch.object(dbmod, "SessionLocal", Local), patch.object(dbmod, "engine", engine), \
         redirect_stdout(out):
        code = migrate.main(list(args))
    return code, out.getvalue()


def test_migration_copies_vectors_onto_their_chunks():
    db, Local, alice, bob = fresh()
    a, a_chunks = legacy_document(db, alice, "a.pdf", 3, "cells")
    b, b_chunks = legacy_document(db, bob, "b.pdf", 1, "history")
    # Position fallback: a chunk whose chroma_id was lost still matches by document_id + chunk_index.
    a_chunks[2].chroma_id = None
    db.commit()
    items = [
        (f"{a.id}-0", axis_vector(0), {"document_id": a.id, "chunk_index": 0}),
        (f"{a.id}-1", axis_vector(0, 0.8, other=5), {"document_id": a.id, "chunk_index": 1}),
        ("old-id", axis_vector(0, 0.7, other=6), {"document_id": a.id, "chunk_index": 2}),
        (f"{b.id}-0", axis_vector(2), {"document_id": b.id, "chunk_index": 0}),
        ("999-0", axis_vector(3), {"document_id": 999, "chunk_index": 0}),  # deleted document
        ("bad", [1.0, 2.0], {"document_id": a.id, "chunk_index": 0}),        # wrong size
    ]
    engine = db.get_bind()

    code, out = run_script(db, Local, engine, FakeChroma(items))
    assert code == 0 and "DRY RUN" in out and "4 vectors to copy" in out and "1 vectors match no chunk" in out, out
    assert vector_count(db) == 0, "a dry run writes nothing"

    code, out = run_script(db, Local, engine, FakeChroma(items), "--apply")
    assert code == 0 and "copied 4 vectors" in out, out
    db.expire_all()
    assert vector_count(db, a.id) == 3 and vector_count(db, b.id) == 1
    assert [r[1] for r in search(db, alice, "cells")] == ["cells 0", "cells 1", "cells 2"]
    assert [r[1] for r in search(db, bob, "history")] == ["history 0"]

    code, out = run_script(db, Local, engine, FakeChroma(items), "--apply")
    assert "0 vectors to copy, 4 chunks already have one" in out and "copied 0 vectors" in out, out
    assert vector_count(db) == 4


def test_migration_reports_and_embeds_chunks_without_a_vector():
    db, Local, alice, _ = fresh()
    a, _ = legacy_document(db, alice, "a.pdf", 2, "genes")
    items = [(f"{a.id}-0", axis_vector(1), {"document_id": a.id, "chunk_index": 0})]
    engine = db.get_bind()
    code, out = run_script(db, Local, engine, FakeChroma(items))
    assert "1 chunks have no vector (search won't find them; use --embed-missing)" in out, out
    with patch("app.services.embedding_service.get_embeddings", side_effect=embed_texts):
        code, out = run_script(db, Local, engine, FakeChroma(items), "--apply", "--embed-missing")
    assert "copied 1 vectors, embedded 1 missing" in out, out
    db.expire_all()
    assert vector_count(db, a.id) == 2


def test_migration_can_skip_chroma_and_embed_everything():
    db, Local, alice, _ = fresh()
    a, _ = legacy_document(db, alice, "a.pdf", 3, "genes")
    engine = db.get_bind()
    db.commit()
    out = io.StringIO()

    def no_chroma(_dir):
        raise AssertionError("Chroma must not be opened with --skip-chroma")

    with patch.object(migrate, "open_collection", no_chroma), \
         patch.object(dbmod, "SessionLocal", Local), patch.object(dbmod, "engine", engine), \
         patch("app.services.embedding_service.get_embeddings", side_effect=embed_texts), \
         patch.dict(sys.modules, {"chromadb": None}), redirect_stdout(out):
        assert migrate.main(["--skip-chroma", "--apply"]) == 0
    assert "no Chroma" in out.getvalue() and "embedded 3 missing" in out.getvalue(), out.getvalue()
    db.expire_all()
    assert vector_count(db, a.id) == 3 and len(search(db, alice, "genes")) == 3


def test_migration_dry_run_works_before_the_table_exists():
    engine = pg_engine(create_tables=False)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id serial PRIMARY KEY, email varchar)"))
        conn.execute(text("CREATE TABLE documents (id serial PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE chunks (id serial PRIMARY KEY, document_id int, content text, chroma_id varchar)"))
        conn.execute(text("INSERT INTO documents DEFAULT VALUES"))
        conn.execute(text("INSERT INTO chunks (document_id, content, chroma_id) VALUES (1, 'x', '1-0')"))
    Local = sessionmaker(bind=engine)
    code, out = run_script(None, Local, engine, FakeChroma([("1-0", axis_vector(0), {})]))
    assert code == 0 and "1 vectors to copy" in out, out


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
