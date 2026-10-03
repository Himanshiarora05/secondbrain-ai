"""Offline checks for quizzes: parsing and validating the model's questions, shuffled options,
citations, coverage, merged quizzes, and the routes that save quizzes and score attempts
(mocked LLM, in-memory SQLite, no network).

Run from backend/:  .venv/Scripts/python.exe tests/test_quiz.py
"""
import json
import os
import random
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-test-key")
os.environ["HF_HUB_OFFLINE"] = "1"

import httpx
import openai
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base
from app.models import Chunk, Document, Quiz, QuizAttempt, QuizQuestion, User
from app.routes import merged_sets as ms
from app.routes import quiz as qr
from app.routes.merged_sets import CreateMergedSetRequest
from app.routes.quiz import AttemptRequest
from app.services.ai import merged_service as mg
from app.services.ai import quiz_service as qs
from app.services.ai import summary_service as ss
from app.services.ai.merged_service import MergedSource
from app.services.ai.summary_service import AIGenerationError

VIDEO = "https://www.youtube.com/watch?v=abcdefghijk"


def reply(content):
    return MagicMock(choices=[MagicMock(finish_reason="stop", message=MagicMock(content=content))])


class FakeLLM:
    """Writes as many questions as the prompt asks for, each citing the first label it was shown.

    The correct option is always written first ("answer": "A"), as models tend to,
    so the code's shuffling is what moves it.
    """

    def __init__(self, fail=None, label=None, replies=None):
        self.fail, self.label, self.replies, self.calls = fail, label, replies, []
        self.chat = MagicMock()
        self.chat.completions.create.side_effect = self._create

    def _create(self, **kw):
        user = kw["messages"][1]["content"]
        self.calls.append(user)
        if self.fail:
            raise self.fail
        if self.replies:
            return reply(self.replies.pop(0))
        n = int(re.search(r"Write (\d+) multiple-choice questions", user).group(1))
        first = re.search(r"\[S(\d+)\]", user).group(1)
        topic = re.search(r"\[S\d+\] (\S+)", user).group(1)
        questions = [{
            "question": f"{topic} question {len(self.calls)}.{i}?",
            "options": [f"Right {i}", f"Wrong a{i}", f"Wrong b{i}", f"Wrong c{i}"],
            "answer": "A",
            "explanation": f"Because the material says Right {i}.",
            "source": self.label or f"S{first}",
        } for i in range(n)]
        return reply(json.dumps(questions))


def api_error(status):
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return openai.APIStatusError("error", response=httpx.Response(status, request=request), body=None)


def right_option(q):
    return q["options"][q["correct_index"]]


# ─── Parsing and validation ───

def test_parse_accepts_the_usual_answer_forms():
    base = {"question": "Q?", "options": ["w", "x", "y", "z"], "explanation": "E.", "source": "S1"}
    for answer, expected in [("B", 1), ("b)", 1), ("(C)", 2), ("D.", 3), (0, 0), ("z", 3), ("C) y", 2)]:
        parsed = qs.parse_quiz_json(json.dumps([{**base, "answer": answer}]))
        assert len(parsed) == 1 and parsed[0]["correct_index"] == expected, (answer, parsed)
    fenced = "```json\n" + json.dumps([{**base, "options": ["A) w", "B) x", "C. y", "(D) z"], "answer": "A"}]) + "\n```"
    parsed = qs.parse_quiz_json("Here you go:\n" + fenced)
    assert parsed[0]["options"] == ["w", "x", "y", "z"], "letters in front of options are removed"
    assert parsed[0]["source"] == "S1" and parsed[0]["explanation"] == "E."


def test_parse_drops_malformed_questions():
    good = {"question": "Q?", "options": ["w", "x", "y", "z"], "answer": "A"}
    bad = [
        {**good, "options": ["w", "x", "y"]},             # three options
        {**good, "options": ["w", "x", "y", "z", "v"]},   # five
        {**good, "options": ["w", "W", "y", "z"]},        # duplicate option
        {**good, "options": ["w", "", "y", "z"]},         # empty option
        {**good, "answer": "E"},                          # no such option
        {**good, "answer": 7},
        {**good, "answer": True},
        {**good, "answer": None},
        {**good, "question": "  "},
        "not an object",
    ]
    parsed = qs.parse_quiz_json(json.dumps(bad + [good]))
    assert len(parsed) == 1 and parsed[0]["explanation"] == "", parsed
    try:
        qs.parse_quiz_json("Sorry, I can't do that.")
    except ValueError:
        pass
    else:
        raise AssertionError("text that isn't JSON raises")


def test_shuffle_keeps_the_right_answer_and_moves_it():
    q = {"question": "Q?", "options": ["Right", "w1", "w2", "w3"], "correct_index": 0, "explanation": ""}
    rng = random.Random(7)
    positions = set()
    for _ in range(40):
        s = qs.shuffle_options(q, rng)
        assert right_option(s) == "Right" and sorted(s["options"]) == sorted(q["options"])
        positions.add(s["correct_index"])
    assert positions == {0, 1, 2, 3}, positions


# ─── Generation ───

def test_cited_quiz_covers_the_source_and_cites_pages():
    chunks = [f"Topic{i} " + "words. " * 60 for i in range(6)]
    citations = [(f"p. {i + 1}", None) for i in range(6)]
    llm = FakeLLM()
    with patch.object(qs, "client", llm), patch.object(qs, "_rng", random.Random(3)):
        quiz = qs.generate_cited_quiz(chunks, citations, count=10)
    assert len(quiz) == 10, len(quiz)
    assert len(llm.calls) == 4, "10 questions, about 3 per call"
    # Four calls over consecutive groups [S0 S1] [S2] [S3] [S4 S5]; the fake cites each group's first label.
    assert {q["source_label"] for q in quiz} == {"p. 1", "p. 3", "p. 4", "p. 5"}, "questions come from the whole source"
    assert all(q["source_url"] is None for q in quiz)
    assert all(right_option(q).startswith("Right") for q in quiz), "the correct index follows its option"
    assert len({q["correct_index"] for q in quiz}) > 1, "the right answer isn't always in the same place"
    assert all(q["explanation"].startswith("Because") for q in quiz)
    assert set(quiz[0]) == {"question", "options", "correct_index", "explanation", "source_label", "source_url"}


def test_youtube_questions_link_to_the_moment():
    citations = [("00:05", f"{VIDEO}&t=5s"), ("02:05", f"{VIDEO}&t=125s")]
    with patch.object(qs, "client", FakeLLM()):
        quiz = qs.generate_cited_quiz(["Intro to cells. " * 10, "Later on, nuclei. " * 10], citations, count=4)
    assert {(q["source_label"], q["source_url"]) for q in quiz} <= set(citations)


def test_a_label_not_in_the_batch_means_no_citation():
    with patch.object(qs, "client", FakeLLM(label="S99")):
        quiz = qs.generate_cited_quiz(["Cells. " * 20], [("p. 1", None)], count=3)
    assert len(quiz) == 3 and all(q["source_label"] is None and q["source_url"] is None for q in quiz)


def test_unusable_replies_and_key_problems():
    garbage = FakeLLM(replies=["no json here", json.dumps([{"question": "Q?", "options": ["a", "b"], "answer": "A"}])])
    with patch.object(qs, "client", garbage):
        try:
            qs.generate_cited_quiz(["Cells. " * 20], [None], count=3)
        except AIGenerationError as e:
            assert "unexpected format" in str(e), e
        else:
            raise AssertionError("no usable questions raises")
    assert len(garbage.calls) == 2, "retried once"

    no_credits = FakeLLM(fail=api_error(402))
    with patch.object(qs, "client", no_credits), patch.object(ss, "logger"):
        try:
            qs.generate_cited_quiz(["Cells. " * 20], [None], count=3)
        except AIGenerationError:
            pass
        else:
            raise AssertionError("402 raises")
    assert len(no_credits.calls) == 1, "a credit problem isn't retried"


def test_document_without_chunks_is_chunked_without_citations():
    with patch.object(qs, "client", FakeLLM()):
        quiz = qs.generate_quiz("Mitochondria make ATP. " * 50, count=5)
    assert len(quiz) == 5 and all(q["source_label"] is None for q in quiz)


def test_merged_quiz_is_grouped_by_source_and_names_it():
    sources = [
        MergedSource(1, "Graph_PPT.pdf", "pdf", None, ["Graphs are pairs. " * 40, "Degree counts. " * 40],
                     [("p. 1", None), ("pp. 2–3", None)], document_id=11),
        MergedSource(2, "YouTube: abc", "youtube", VIDEO, ["Video intro. " * 20], [("00:05", f"{VIDEO}&t=5s")], document_id=12),
        MergedSource(3, "notes.docx", "docx", None, ["Word notes. " * 20], [None], document_id=13),
    ]
    llm = FakeLLM()
    with patch.object(qs, "client", llm):
        quiz = mg.generate_merged_quiz(sources, count=10)
    assert len(quiz) == 10
    order = [q["document_id"] for q in quiz]
    assert order == sorted(order) and set(order) == {11, 12, 13}, order
    by_doc = {q["document_id"]: q for q in quiz}
    assert by_doc[11]["source_label"] in ("Graph_PPT.pdf · p. 1", "Graph_PPT.pdf · pp. 2–3")
    assert (by_doc[12]["source_label"], by_doc[12]["source_url"]) == ("YouTube: abc · 00:05", f"{VIDEO}&t=5s")
    assert (by_doc[13]["source_label"], by_doc[13]["source_url"]) == ("notes.docx", None)
    for prompt in llm.calls:
        assert len(set(re.findall(r"\[S\d+\] (\S+)", prompt))) == 1, "a call mixed sources"


# ─── Routes (in-memory SQLite) ───

def fresh_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    owner = User(email="owner@example.com", password_hash="not-used")
    other = User(email="other@example.com", password_hash="not-used")
    db.add_all([owner, other])
    db.commit()
    db.info["user"], db.info["other"] = owner, other
    return db


def add_doc(db, name, source_type, chunks, pages=None, starts=None, url=None, user=None):
    owner = user or db.info["user"]
    doc = Document(user_id=owner.id, file_id=f"f-{name}", filename=name, content=" ".join(chunks) or "Some text.",
                   source_type=source_type, source_url=url)
    db.add(doc)
    db.flush()
    for i, text in enumerate(chunks):
        p = pages[i] if pages else (None, None)
        db.add(Chunk(document_id=doc.id, content=text, page_start=p[0], page_end=p[1],
                     start_seconds=starts[i] if starts else None))
    db.commit()
    return doc.id


def call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except HTTPException as e:
        return e


def test_document_quiz_generate_answer_and_keep_history():
    db = fresh_db()
    user = db.info["user"]
    pdf = add_doc(db, "cells.pdf", "pdf", [f"Topic{i} cells. " * 30 for i in range(4)], pages=[(1, 1), (2, 2), (3, 4), (5, 5)])
    assert qr.get_document_quiz(pdf, db=db, user=user) == {"document_id": pdf, "set_id": None, "quiz": None, "attempts": []}

    with patch.object(qs, "client", FakeLLM()):
        state = qr.create_document_quiz(pdf, count=10, db=db, user=user)
    quiz = state["quiz"]
    assert len(quiz["questions"]) == 10 and state["attempts"] == [] and quiz["stale"] is False
    assert all(q["source_label"] in ("p. 1", "p. 2", "pp. 3–4", "p. 5") for q in quiz["questions"]), quiz
    assert all(len(q["options"]) == 4 and q["explanation"] for q in quiz["questions"])
    assert qr.get_document_quiz(pdf, db=db, user=user)["quiz"] == quiz, "saved as returned"

    # Score: 7 right, 2 wrong, 1 skipped.
    questions = quiz["questions"]
    answers = [q["correct_index"] for q in questions[:7]] + [(q["correct_index"] + 1) % 4 for q in questions[7:9]] + [None]
    res = qr.submit_document_attempt(pdf, quiz["id"], AttemptRequest(answers=answers), db=db, user=user)
    assert (res["attempt"]["score"], res["attempt"]["total"]) == (7, 10), res["attempt"]
    assert res["attempt"]["answers"] == answers and res["attempts"][0]["id"] == res["attempt"]["id"]

    for bad in ([0] * 9, [0] * 9 + [4], [0] * 9 + [-1]):
        err = call(qr.submit_document_attempt, pdf, quiz["id"], AttemptRequest(answers=bad), db=db, user=user)
        assert isinstance(err, HTTPException) and err.status_code == 400, (bad, err)
    assert db.query(QuizAttempt).count() == 1, "rejected attempts aren't saved"

    # A new quiz doesn't replace the old one: its attempt keeps its questions.
    with patch.object(qs, "client", FakeLLM()):
        second = qr.create_document_quiz(pdf, count=5, db=db, user=user)
    assert second["quiz"]["id"] != quiz["id"] and len(second["quiz"]["questions"]) == 5
    assert [a["quiz_id"] for a in second["attempts"]] == [quiz["id"]], "earlier attempts are still listed"
    assert db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz["id"]).count() == 10
    perfect = [q["correct_index"] for q in second["quiz"]["questions"]]
    res = qr.submit_document_attempt(pdf, second["quiz"]["id"], AttemptRequest(answers=perfect), db=db, user=user)
    assert res["attempt"]["score"] == 5 and [a["score"] for a in res["attempts"]] == [5, 7], "newest first"
    # Answering the old quiz is still allowed.
    res = qr.submit_document_attempt(pdf, quiz["id"], AttemptRequest(answers=[None] * 10), db=db, user=user)
    assert res["attempt"]["score"] == 0


def test_quizzes_are_private_and_tied_to_their_document():
    db = fresh_db()
    user, other = db.info["user"], db.info["other"]
    mine = add_doc(db, "mine.pdf", "pdf", ["Cells. " * 30], pages=[(1, 1)])
    second = add_doc(db, "second.pdf", "pdf", ["Genes. " * 30], pages=[(1, 1)])
    with patch.object(qs, "client", FakeLLM()):
        quiz = qr.create_document_quiz(mine, count=3, db=db, user=user)["quiz"]
    answers = AttemptRequest(answers=[0, 0, 0])
    for fn, args in [
        (qr.get_document_quiz, (mine,)),
        (qr.create_document_quiz, (mine,)),
        (qr.submit_document_attempt, (mine, quiz["id"], answers)),
    ]:
        kwargs = {"db": db, "user": other}
        if fn is qr.create_document_quiz:
            kwargs["count"] = 3
        err = call(fn, *args, **kwargs)
        assert isinstance(err, HTTPException) and err.status_code == 404 and err.detail == "Document not found", (fn, err)
    err = call(qr.submit_document_attempt, second, quiz["id"], answers, db=db, user=user)
    assert isinstance(err, HTTPException) and err.status_code == 404 and err.detail == "Quiz not found", \
        "a quiz is only answered through its own document"
    assert db.query(QuizAttempt).count() == 0


def test_failure_saves_nothing_and_deleting_the_document_removes_its_quizzes():
    db = fresh_db()
    user = db.info["user"]
    doc = add_doc(db, "slides.pptx", "pptx", ["[Slide 1] Qubits. " * 10, "[Slide 2] Gates. " * 10])
    with patch.object(qs, "client", FakeLLM(fail=api_error(402))), patch.object(ss, "logger"):
        err = call(qr.create_document_quiz, doc, count=4, db=db, user=user)
    assert isinstance(err, HTTPException) and err.status_code == 502 and err.detail, err
    assert db.query(Quiz).count() == 0
    with patch.object(qs, "client", FakeLLM(replies=["[]", "[]"])):
        err = call(qr.create_document_quiz, doc, count=4, db=db, user=user)
    assert isinstance(err, HTTPException) and err.status_code == 502, err

    with patch.object(qs, "client", FakeLLM()):
        quiz = qr.create_document_quiz(doc, count=4, db=db, user=user)["quiz"]
    assert {q["source_label"] for q in quiz["questions"]} <= {"Slide 1", "Slide 2"}
    qr.submit_document_attempt(doc, quiz["id"], AttemptRequest(answers=[0, 1, 2, 3]), db=db, user=user)
    db.delete(db.get(Document, doc))
    db.commit()
    assert (db.query(Quiz).count(), db.query(QuizQuestion).count(), db.query(QuizAttempt).count()) == (0, 0, 0)


def test_document_without_chunks_or_text():
    db = fresh_db()
    user = db.info["user"]
    plain = add_doc(db, "old.docx", "docx", [])
    with patch.object(qs, "client", FakeLLM()):
        quiz = qr.create_document_quiz(plain, count=2, db=db, user=user)["quiz"]
    assert len(quiz["questions"]) == 2 and all(q["source_label"] is None for q in quiz["questions"])
    empty = Document(user_id=user.id, file_id="empty", filename="empty.pdf", content="  ", source_type="pdf")
    db.add(empty)
    db.commit()
    err = call(qr.create_document_quiz, empty.id, count=2, db=db, user=user)
    assert isinstance(err, HTTPException) and err.status_code == 400, err


def test_merged_quiz_route_and_staleness():
    db = fresh_db()
    user = db.info["user"]
    pdf = add_doc(db, "Graph_PPT.pdf", "pdf", ["Graphs are pairs. " * 10, "Degree counts edges. " * 10], pages=[(1, 1), (2, 3)])
    ppt = add_doc(db, "quantum.pptx", "pptx", ["[Slide 1] Qubits. " * 10, "[Slide 2] Gates. " * 10])
    vid = add_doc(db, "YouTube: abcdefghijk", "youtube", ["Intro. " * 10, "Later. " * 10], starts=[5, 125], url=VIDEO)
    set_id = ms.create_merged_set(CreateMergedSetRequest(document_ids=[pdf, ppt, vid]), db=db, user=user)["merged_set"]["id"]
    assert qr.get_merged_quiz(set_id, db=db, user=user)["quiz"] is None

    with patch.object(qs, "client", FakeLLM()):
        state = qr.create_merged_quiz(set_id, count=6, db=db, user=user)
    quiz = state["quiz"]
    assert state["set_id"] == set_id and len(quiz["questions"]) == 6
    assert {q["document_id"] for q in quiz["questions"]} == {pdf, ppt, vid}
    labels = {q["source_label"] for q in quiz["questions"]}
    assert "Graph_PPT.pdf · p. 1" in labels and "quantum.pptx · Slide 1" in labels, labels
    assert any(q["source_url"] == f"{VIDEO}&t=5s" for q in quiz["questions"])

    res = qr.submit_merged_attempt(set_id, quiz["id"], AttemptRequest(answers=[q["correct_index"] for q in quiz["questions"]]),
                                   db=db, user=user)
    assert res["attempt"]["score"] == 6

    err = call(qr.get_merged_quiz, set_id, db=db, user=db.info["other"])
    assert isinstance(err, HTTPException) and err.status_code == 404 and err.detail == "Merged set not found"

    db.delete(db.get(Document, ppt))
    db.commit()
    db.expire_all()
    stale = qr.get_merged_quiz(set_id, db=db, user=user)
    assert stale["quiz"]["stale"] is True and len(stale["quiz"]["questions"]) == 6, "questions stay, unlinked"
    assert len(stale["attempts"]) == 1
    with patch.object(qs, "client", FakeLLM()):
        fresh = qr.create_merged_quiz(set_id, count=4, db=db, user=user)
    assert fresh["quiz"]["stale"] is False and {q["document_id"] for q in fresh["quiz"]["questions"]} == {pdf, vid}

    db.delete(db.get(Document, vid))
    db.commit()
    err = call(qr.create_merged_quiz, set_id, count=4, db=db, user=user)
    assert isinstance(err, HTTPException) and err.status_code == 400 and "fewer than 2" in err.detail
    ms.delete_merged_set(set_id, db=db, user=user)
    assert (db.query(Quiz).count(), db.query(QuizAttempt).count()) == (0, 0), "deleting the set removes its quizzes"


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
