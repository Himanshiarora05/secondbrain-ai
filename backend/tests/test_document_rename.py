"""Offline checks for renaming a document (mocked DB, no network).

Search reads the name from the document row, so renaming only writes that row;
tests/test_pgvector_store.py checks search shows the new name.

Run from backend/:  .venv/Scripts/python.exe tests/test_document_rename.py
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ["HF_HUB_OFFLINE"] = "1"

from fastapi import HTTPException

from types import SimpleNamespace

# The signed-in user the route functions are called for (routes take it from get_current_user).
TEST_USER = SimpleNamespace(id=1)

from app.routes import documents
from app.routes.documents import RenameRequest, rename_document


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


def test_rename_updates_the_document():
    doc = _doc(101, "test_fresh_upload.pdf")
    db = _db(doc)
    result = _call(101, "OOPsfile.pdf", db)
    assert result == {"id": 101, "filename": "OOPsfile.pdf"}, result
    assert doc.filename == "OOPsfile.pdf"
    db.commit.assert_called_once()


def test_whitespace_is_tidied():
    doc = _doc(103, "a.pdf")
    assert _call(103, "  Java   lab\tfile.pdf \n", _db(doc))["filename"] == "Java lab file.pdf"
    assert doc.filename == "Java lab file.pdf"


def test_empty_or_too_long_names_are_refused():
    for bad, msg in [("", "empty"), ("   \t ", "empty"), ("x" * 256, "255")]:
        db = _db(_doc(104, "keep.pdf"))
        result = _call(104, bad, db)
        assert isinstance(result, HTTPException) and result.status_code == 400 and msg in result.detail, (bad, result)
        db.commit.assert_not_called()
    assert _call(104, "y" * 255, _db(_doc(104, "keep.pdf")))["filename"] == "y" * 255


def test_missing_document_is_404():
    result = _call(999, "whatever.pdf", _db(None))
    assert isinstance(result, HTTPException) and result.status_code == 404


def test_same_name_writes_nothing():
    db = _db(_doc(105, "same.pdf"))
    assert _call(105, " same.pdf ", db) == {"id": 105, "filename": "same.pdf"}
    db.commit.assert_not_called()


def test_database_failure_is_a_500_and_rolls_back():
    doc = _doc(107, "before.pdf")
    db = _db(doc)
    db.commit.side_effect = RuntimeError("connection lost")
    with patch.object(documents, "logger"):
        result = _call(107, "after.pdf", db)
    assert isinstance(result, HTTPException) and result.status_code == 500, result
    db.rollback.assert_called_once()


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
