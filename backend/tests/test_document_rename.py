"""Offline checks for renaming a document (mocked DB, throwaway Chroma, no network).

Run from backend/:  .venv/Scripts/python.exe tests/test_document_rename.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database, vector store or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"

from fastapi import HTTPException

from types import SimpleNamespace

# The signed-in user the route functions are called for (routes take it from get_current_user).
TEST_USER = SimpleNamespace(id=1)

from app.database.chroma import get_collection
from app.routes import documents
from app.routes.documents import RenameRequest, rename_document

col = get_collection()


def _seed(doc_id, filename, n=3):
    ids = [f"{doc_id}-{i}" for i in range(n)]
    col.upsert(
        ids=ids,
        embeddings=[[float(i + 1), 0.5, 0.25] for i in range(n)],
        documents=[f"chunk {i}" for i in range(n)],
        metadatas=[{"document_id": doc_id, "filename": filename, "source_type": "pdf",
                    "chunk_index": i, "page_start": i + 1, "page_end": i + 1} for i in range(n)],
    )
    return ids


def _db(doc):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = doc
    return db


def _doc(doc_id, filename):
    doc = MagicMock(id=doc_id)
    doc.filename = filename
    return doc


def _call(doc_id, name, db):
    try:
        return rename_document(doc_id, RenameRequest(filename=name), db=db, user=TEST_USER)
    except HTTPException as e:
        return e


def _names(doc_id):
    return [m["filename"] for m in col.get(where={"document_id": doc_id}, include=["metadatas"])["metadatas"]]


def test_rename_updates_database_and_every_search_vector():
    _seed(101, "test_fresh_upload.pdf")
    _seed(102, "other.pdf")
    doc = _doc(101, "test_fresh_upload.pdf")
    db = _db(doc)
    result = _call(101, "OOPsfile.pdf", db)
    assert result == {"id": 101, "filename": "OOPsfile.pdf"}, result
    assert doc.filename == "OOPsfile.pdf"
    db.commit.assert_called_once()
    assert _names(101) == ["OOPsfile.pdf"] * 3
    assert _names(102) == ["other.pdf"] * 3, "another document's vectors changed"
    meta = col.get(ids=["101-1"], include=["metadatas"])["metadatas"][0]
    assert (meta["page_start"], meta["chunk_index"], meta["source_type"]) == (2, 1, "pdf"), meta


def test_whitespace_is_tidied():
    _seed(103, "a.pdf")
    doc = _doc(103, "a.pdf")
    assert _call(103, "  Java   lab\tfile.pdf \n", _db(doc))["filename"] == "Java lab file.pdf"
    assert _names(103) == ["Java lab file.pdf"] * 3


def test_empty_or_too_long_names_are_refused():
    _seed(104, "keep.pdf")
    for bad, msg in [("", "empty"), ("   \t ", "empty"), ("x" * 256, "255")]:
        db = _db(_doc(104, "keep.pdf"))
        result = _call(104, bad, db)
        assert isinstance(result, HTTPException) and result.status_code == 400 and msg in result.detail, (bad, result)
        db.commit.assert_not_called()
    assert _names(104) == ["keep.pdf"] * 3
    assert _call(104, "y" * 255, _db(_doc(104, "keep.pdf")))["filename"] == "y" * 255


def test_missing_document_is_404():
    result = _call(999, "whatever.pdf", _db(None))
    assert isinstance(result, HTTPException) and result.status_code == 404


def test_same_name_writes_nothing():
    _seed(105, "same.pdf")
    db = _db(_doc(105, "same.pdf"))
    with patch.object(col, "update") as update:
        assert _call(105, " same.pdf ", db) == {"id": 105, "filename": "same.pdf"}
    update.assert_not_called()
    db.commit.assert_not_called()


def test_document_without_vectors_is_renamed():
    doc = _doc(106, "empty.docx")
    assert _call(106, "Notes.docx", _db(doc))["filename"] == "Notes.docx"
    assert doc.filename == "Notes.docx"


def test_database_failure_puts_search_names_back():
    _seed(107, "before.pdf")
    doc = _doc(107, "before.pdf")
    db = _db(doc)
    db.commit.side_effect = RuntimeError("connection lost")
    with patch.object(documents, "logger"):
        result = _call(107, "after.pdf", db)
    assert isinstance(result, HTTPException) and result.status_code == 500, result
    db.rollback.assert_called_once()
    assert _names(107) == ["before.pdf"] * 3


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
