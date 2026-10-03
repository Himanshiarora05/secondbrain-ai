"""Offline checks that summary/flashcard saves survive two requests at once (mocked DB and LLM).

The real race needs Postgres row locks; these check the route logic around them:
lock the document before writing, re-read what another request may have saved,
and never insert a second summary.

Run from backend/:  .venv/Scripts/python.exe tests/test_concurrent_generation.py
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-test-key")
os.environ["HF_HUB_OFFLINE"] = "1"

from types import SimpleNamespace

# The signed-in user the route functions are called for (routes take it from get_current_user).
TEST_USER = SimpleNamespace(id=1)

from app.routes import study
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.flashcard import Flashcard
from app.models.summary import Summary


class FakeDB:
    """Just enough of a Session for the study routes; records the order of operations."""

    def __init__(self, doc, summaries=(), chunks=()):
        self.doc = doc
        self.summaries = list(summaries)  # successive results of the Summary lookup
        self.chunks = list(chunks)
        self.log = []
        self.added = []

    def query(self, model):
        q = MagicMock()
        if model is Document:
            q.filter.return_value.first.return_value = self.doc
        elif model is Document.id:  # the row lock
            def lock():
                self.log.append("lock")
                return (self.doc.id,)
            q.filter.return_value.with_for_update.return_value.first.side_effect = lock
        elif model is Summary:
            def next_summary():
                self.log.append("read summary")
                return self.summaries.pop(0) if self.summaries else None
            q.filter.return_value.first.side_effect = next_summary
        elif model is Chunk:
            q.filter.return_value.order_by.return_value.all.return_value = self.chunks
        elif model is Flashcard:
            q.filter.return_value.delete.side_effect = lambda: self.log.append("delete cards")
            q.filter.return_value.order_by.return_value.all.side_effect = lambda: [
                MagicMock(id=i, question=c.question, answer=c.answer, source_label=None, source_url=None)
                for i, c in enumerate(self.added, start=1)
            ]
        return q

    def add(self, obj):
        self.log.append(f"add {type(obj).__name__}")
        self.added.append(obj)

    def add_all(self, objs):
        self.log.append(f"add {len(objs)} cards")
        self.added.extend(objs)

    def commit(self):
        self.log.append("commit")

    def refresh(self, obj):
        pass


def _doc():
    doc = MagicMock(id=7, content="Some text to summarise.", source_type="pdf", source_url=None)
    doc.filename = "notes.pdf"
    return doc


def test_summary_saved_by_another_request_is_kept_not_duplicated():
    other = MagicMock(content="Summary saved first by the other request")
    db = FakeDB(_doc(), summaries=[None, other])  # none at start, one after generating
    with patch.object(study, "generate_summary", return_value="My late summary"):
        result = study.create_or_regenerate_summary(7, regenerate=False, db=db, user=TEST_USER)
    assert result["summary"] == "Summary saved first by the other request"
    assert not db.added, f"must not insert a second summary: {db.log}"
    assert db.log.index("lock") < db.log.index("read summary", 1), db.log  # re-read happens under the lock


def test_regenerate_overwrites_a_summary_saved_meanwhile():
    other = MagicMock(content="old")
    db = FakeDB(_doc(), summaries=[None, other])
    with patch.object(study, "generate_summary", return_value="Fresh summary"):
        result = study.create_or_regenerate_summary(7, regenerate=True, db=db, user=TEST_USER)
    assert result["summary"] == "Fresh summary" and other.content == "Fresh summary"
    assert not db.added


def test_first_summary_is_inserted_under_the_lock():
    db = FakeDB(_doc(), summaries=[None, None])
    with patch.object(study, "generate_summary", return_value="First summary"):
        result = study.create_or_regenerate_summary(7, regenerate=False, db=db, user=TEST_USER)
    assert result["summary"] == "First summary"
    assert db.log == ["read summary", "lock", "read summary", "add Summary", "commit"], db.log


def test_llm_is_not_called_under_the_lock():
    db = FakeDB(_doc(), summaries=[None, None])

    def generate(_text):
        assert "lock" not in db.log, "the row lock must not be held during the slow LLM call"
        return "Summary"

    with patch.object(study, "generate_summary", side_effect=generate):
        study.create_or_regenerate_summary(7, regenerate=False, db=db, user=TEST_USER)


def test_flashcard_replace_locks_before_deleting():
    db = FakeDB(_doc(), chunks=[])  # no chunks: falls back to generate_flashcards(doc.content)
    cards = [{"question": "Q1?", "answer": "A1."}, {"question": "Q2?", "answer": "A2."}]
    with patch.object(study, "generate_flashcards", return_value=cards):
        result = study.create_flashcards(7, count=2, db=db, user=TEST_USER)
    assert db.log == ["lock", "delete cards", "add 2 cards", "commit"], db.log
    assert [c["question"] for c in result["flashcards"]] == ["Q1?", "Q2?"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
