"""Offline checks that summary AI calls run a few at a time, keep their order, and stop on the
first failure (mocked LLM with small delays; no network).

Run from backend/:  .venv/Scripts/python.exe tests/test_parallel_calls.py
"""
import os
import random
import re
import sys
import tempfile
import threading
import time
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
os.environ.pop("SUMMARY_PARALLEL_CALLS", None)

from app.services.ai import merged_service as mg
from app.services.ai import summary_service as ss
from app.services.ai.merged_service import MergedSource


class Tracker:
    """Records how many calls run at the same time."""

    def __init__(self):
        self.active = self.peak = self.started = 0
        self.lock = threading.Lock()

    def __enter__(self):
        with self.lock:
            self.active += 1
            self.started += 1
            self.peak = max(self.peak, self.active)

    def __exit__(self, *exc):
        with self.lock:
            self.active -= 1


def test_setting():
    assert ss.parallel_calls() == ss.DEFAULT_PARALLEL_CALLS == 4
    for value, expected in [("1", 1), ("8", 8), ("99", ss.MAX_PARALLEL_CALLS), ("0", 1), ("-3", 1), ("many", 4), ("", 4)]:
        with patch.dict(os.environ, {"SUMMARY_PARALLEL_CALLS": value}):
            assert ss.parallel_calls() == expected, value


def test_runs_a_few_at_a_time_and_keeps_order():
    tracker = Tracker()

    def work(i):
        with tracker:
            time.sleep(random.uniform(0.01, 0.05))
            return i * 10

    assert ss.run_calls(work, range(20)) == [i * 10 for i in range(20)]
    assert 1 < tracker.peak <= 4, tracker.peak
    with patch.dict(os.environ, {"SUMMARY_PARALLEL_CALLS": "1"}):
        tracker.peak = 0
        assert ss.run_calls(work, range(5)) == [0, 10, 20, 30, 40]
        assert tracker.peak == 1


def test_first_failure_stops_the_rest():
    tracker = Tracker()

    def work(i):
        with tracker:
            time.sleep(0.02)
            if i == 1:
                raise ss.AIGenerationError("The AI service is out of credits.")
            return i

    with patch.dict(os.environ, {"SUMMARY_PARALLEL_CALLS": "2"}):
        try:
            ss.run_calls(work, range(30))
            raise AssertionError("expected the failure")
        except ss.AIGenerationError as e:
            assert "out of credits" in str(e)
    assert tracker.started < 10, f"{tracker.started} of 30 calls started after the failure"


def test_no_items_and_one_item():
    assert ss.run_calls(lambda i: i, []) == []
    assert ss.run_calls(lambda i: i + 1, [1]) == [2]


def fake_llm(tracker, delay=0.03):
    def create(**kw):
        system, user = kw["messages"][0]["content"], kw["messages"][1]["content"]
        with tracker:
            time.sleep(delay)
        labels = " ".join(dict.fromkeys(re.findall(r"\[S\d+\]", user)))
        text = f"- All {labels}" if system.startswith("You are an expert study assistant creating") else f"- note {labels}"
        return MagicMock(choices=[MagicMock(finish_reason="stop", message=MagicMock(content=text))])

    llm = MagicMock()
    llm.chat.completions.create.side_effect = create
    return llm


def test_merged_map_calls_run_in_parallel_with_correct_citations():
    sources = [MergedSource(n, f"book{n}.pdf", "pdf", None, [f"Book {n} part {i}. " + "w" * 900 for i in range(12)],
                            [(f"p. {i + 1}", None) for i in range(12)], document_id=n) for n in (1, 2)]
    tracker = Tracker()
    with patch.object(ss, "client", fake_llm(tracker)):
        out = mg.generate_merged_summary(sources)
    assert tracker.peak > 1, "map calls overlapped"
    body = out.split("\n\n---\n\n")[1]
    # Every label came back from its own batch, so each source cites all 12 of its pages.
    assert "1: p. 1, p. 2" in body and "2: p. 1" in body and "p. 12" in body, body[:400]


def test_single_document_map_calls_run_in_parallel():
    tracker = Tracker()
    with patch.object(ss, "client", fake_llm(tracker)):
        out = ss.generate_cited_summary([f"Part {i}. " + "v" * 900 for i in range(20)], [(f"p. {i + 1}", None) for i in range(20)])
    assert tracker.peak > 1 and "(p. 1; p. 2" in out and "p. 20)" in out, out[:300]
    tracker = Tracker()
    with patch.object(ss, "client", fake_llm(tracker)):
        ss.generate_summary("A plain sentence about cells. " * 1_500)
    assert tracker.peak > 1


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
