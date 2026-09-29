"""Offline checks for scripts/assign_documents_to_user.py (in-memory SQLite, throwaway Chroma; no network).

Run from backend/:  .venv/Scripts/python.exe tests/test_assign_documents.py
"""
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database, vector store or model hub.
os.environ["DATABASE_URL"] = "postgresql://offline:offline@127.0.0.1:1/offline"
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database.db as dbmod
from app.database.chroma import get_collection
from app.database.db import Base
from app.models import Chunk, Document, MergedSet, MergedSetDocument, User
from scripts import assign_documents_to_user as script

collection = get_collection()


def fresh():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Local()
    me = User(email="me@example.com", password_hash="x")
    other = User(email="other@example.com", password_hash="x")
    db.add_all([me, other])
    db.commit()
    for existing in collection.get(include=[])["ids"]:
        collection.delete(ids=[existing])
    return db, Local, me, other


def add_doc(db, name, owner=None, chunks=2):
    doc = Document(file_id=f"f-{name}", filename=name, content="text", source_type="pdf", user_id=owner)
    db.add(doc)
    db.flush()
    ids = [f"{doc.id}-{i}" for i in range(chunks)]
    for i, cid in enumerate(ids):
        db.add(Chunk(document_id=doc.id, content=f"chunk {i}", chroma_id=cid, page_start=i + 1, page_end=i + 1))
    meta = {"document_id": doc.id, "filename": name, "source_type": "pdf", "page_start": 1, "page_end": 1}
    if owner is not None:
        meta["user_id"] = owner
    collection.add(ids=ids, embeddings=[[1.0, 0.5, float(i)] for i in range(chunks)],
                   documents=[f"chunk {i}" for i in range(chunks)], metadatas=[dict(meta) for _ in ids])
    db.commit()
    return doc.id


def add_set(db, name, doc_ids, owner=None):
    s = MergedSet(name=name, user_id=owner)
    s.members = [MergedSetDocument(document_id=d, position=i) for i, d in enumerate(doc_ids)]
    db.add(s)
    db.commit()
    return s.id


def run(Local, *args):
    out = io.StringIO()
    with patch.object(dbmod, "SessionLocal", Local), redirect_stdout(out):
        code = script.main(list(args))
    return code, out.getvalue()


def owners(db):
    db.expire_all()
    return ({d.filename: d.user_id for d in db.query(Document)}, {s.name: s.user_id for s in db.query(MergedSet)})


def vector_owners(doc_id):
    return [m.get("user_id") for m in collection.get(where={"document_id": doc_id}, include=["metadatas"])["metadatas"]]


def test_dry_run_changes_nothing():
    db, Local, me, other = fresh()
    a = add_doc(db, "old-a.pdf")
    add_doc(db, "old-b.pdf", chunks=3)
    add_doc(db, "theirs.pdf", owner=other.id)
    add_set(db, "old set", [a])
    code, out = run(Local, "--email", "ME@example.com")
    assert code == 0 and "DRY RUN" in out and "2 document(s) without an owner" in out, out
    assert "old-b.pdf" in out and "3 chunks,   3 search vectors" in out and "theirs.pdf" not in out, out
    assert "1 merged set(s) without an owner" in out and "--apply" in out
    docs, sets = owners(db)
    assert docs == {"old-a.pdf": None, "old-b.pdf": None, "theirs.pdf": other.id} and sets == {"old set": None}
    assert vector_owners(a) == [None, None]


def test_apply_assigns_documents_vectors_and_sets():
    db, Local, me, other = fresh()
    a = add_doc(db, "old-a.pdf")
    b = add_doc(db, "old-b.pdf", chunks=3)
    t = add_doc(db, "theirs.pdf", owner=other.id)
    add_set(db, "old set", [a, b])
    add_set(db, "their set", [t], owner=other.id)
    code, out = run(Local, "--email", "me@example.com", "--apply")
    assert code == 0 and "2 document(s) (5 search vectors) and 1 merged set(s) assigned to me@example.com, 0 failed" in out, out
    docs, sets = owners(db)
    assert docs == {"old-a.pdf": me.id, "old-b.pdf": me.id, "theirs.pdf": other.id}
    assert sets == {"old set": me.id, "their set": other.id}
    assert vector_owners(a) == [me.id] * 2 and vector_owners(b) == [me.id] * 3 and vector_owners(t) == [other.id] * 2
    meta = collection.get(ids=[f"{a}-1"], include=["metadatas"])["metadatas"][0]
    assert (meta["filename"], meta["page_start"], meta["document_id"]) == ("old-a.pdf", 1, a), "other metadata kept"


def test_running_twice_is_safe():
    db, Local, me, _ = fresh()
    add_doc(db, "old-a.pdf")
    run(Local, "--email", "me@example.com", "--apply")
    code, out = run(Local, "--email", "me@example.com", "--apply")
    assert code == 0 and "Nothing to do." in out, out


def test_owned_documents_are_never_reassigned():
    db, Local, me, other = fresh()
    t = add_doc(db, "theirs.pdf", owner=other.id)
    code, out = run(Local, "--email", "me@example.com", "--apply")
    assert "Nothing to do." in out
    assert owners(db)[0] == {"theirs.pdf": other.id} and vector_owners(t) == [other.id] * 2


def test_a_set_mixing_in_someone_elses_document_is_skipped():
    db, Local, me, other = fresh()
    a = add_doc(db, "old-a.pdf")
    t = add_doc(db, "theirs.pdf", owner=other.id)
    add_set(db, "mixed", [a, t])
    code, out = run(Local, "--email", "me@example.com", "--apply")
    assert "skipped: a document in it belongs to another account" in out, out
    assert owners(db)[1] == {"mixed": None}
    assert owners(db)[0]["old-a.pdf"] == me.id


def test_unknown_email_is_explained():
    db, Local, *_ = fresh()
    add_doc(db, "old-a.pdf")
    code, out = run(Local, "--email", "nobody@example.com")
    assert code == 2 and "Sign up in the app first" in out
    assert owners(db)[0] == {"old-a.pdf": None}


def test_a_failed_commit_puts_the_vectors_back():
    db, Local, me, _ = fresh()
    a = add_doc(db, "old-a.pdf")
    session = Local()
    with patch.object(session, "commit", side_effect=RuntimeError("database went away")):
        try:
            script.assign_document(session, collection, a, me.id)
            raise AssertionError("expected the failure to propagate")
        except RuntimeError:
            pass
    assert vector_owners(a) == [None, None], "Chroma metadata restored"
    assert owners(db)[0] == {"old-a.pdf": None}


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
