"""Offline checks that AI failures reach the user as plain messages, not raw API errors (mocked LLM, no DB).

Run from backend/:  .venv/Scripts/python.exe tests/test_ai_error_messages.py
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

import httpx
import openai
from fastapi import HTTPException

from types import SimpleNamespace

# The signed-in user the route functions are called for (routes take it from get_current_user).
TEST_USER = SimpleNamespace(id=1)

from app.services.ai import summary_service as ss
from app.services.ai import flashcard_service as fs
from app.services import search_service
from app.routes import search as search_route
from app.routes import study
from app.models.chunk import Chunk
from app.models.document import Document

REQ = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
RAW_402 = ("{'error': {'message': 'Insufficient credits. This account never purchased credits.', "
           "'code': 402, 'metadata': {'limit_source': 'openrouter_credits'}}}")


def status_error(code, body=RAW_402):
    return openai.APIStatusError(f"Error code: {code} - {body}", response=httpx.Response(code, request=REQ), body=None)


def failing_client(exc):
    client = MagicMock()
    client.chat.completions.create.side_effect = exc
    return client


def assert_plain(message):
    for raw in ("Error code", "{'error'", "metadata", "Traceback"):
        assert raw not in message, f"raw error leaked into: {message}"


def test_each_failure_kind_has_a_plain_message():
    cases = [
        (status_error(402), "out of credits"),
        (status_error(401), "rejected the API key"),
        (status_error(403), "refused this request"),
        (status_error(404), "model isn't available"),
        (status_error(429), "rate limit"),
        (status_error(500), "having problems"),
        (status_error(503), "having problems"),
        (openai.APITimeoutError(request=REQ), "took too long"),
        (openai.APIConnectionError(request=REQ), "Could not reach the AI service"),
        (status_error(400), "couldn't complete this request"),
        (RuntimeError("something odd"), "couldn't complete this request"),
    ]
    for exc, expected in cases:
        msg = ss.ai_error_message(exc)
        assert expected in msg, (type(exc).__name__, getattr(exc, "status_code", None), msg)
        assert_plain(msg)


def test_summary_failure_is_plain_and_keeps_the_raw_cause():
    with patch.object(ss, "client", failing_client(status_error(402))):
        try:
            ss.generate_summary("Short text about mitochondria.")
        except ss.AIGenerationError as e:
            assert str(e).startswith("The AI service is out of credits"), str(e)
            assert isinstance(e.__cause__, openai.APIStatusError), "raw error should stay chained for debugging"
        else:
            raise AssertionError("expected AIGenerationError")


def test_long_summary_map_step_and_youtube_summary_are_plain_too():
    with patch.object(ss, "client", failing_client(status_error(402))):
        for call in (lambda: ss.generate_summary("Sentence about cells. " * 400),
                     lambda: ss.generate_youtube_summary([(0, "Intro."), (60, "More.")], "https://youtu.be/abcdefghijk")):
            try:
                call()
            except ss.AIGenerationError as e:
                assert "out of credits" in str(e)
                assert_plain(str(e))
            else:
                raise AssertionError("expected AIGenerationError")


def test_flashcards_do_not_retry_a_credit_error():
    client = failing_client(status_error(402))
    with patch.object(fs, "client", client):
        try:
            fs.generate_flashcards("Some text about cells.", count=3)
        except ss.AIGenerationError as e:
            assert "out of credits" in str(e)
        else:
            raise AssertionError("expected AIGenerationError")
    assert client.chat.completions.create.call_count == 1, "a 402 can't be fixed by retrying"


def test_flashcards_retry_once_then_explain_a_rate_limit():
    client = failing_client(status_error(429))
    with patch.object(fs, "client", client):
        try:
            fs.generate_flashcards("Some text about cells.", count=3)
        except ss.AIGenerationError as e:
            assert "rate limit" in str(e)
        else:
            raise AssertionError("expected AIGenerationError")
    assert client.chat.completions.create.call_count == 2


def test_flashcards_unusable_reply_has_its_own_message():
    reply = MagicMock()
    reply.choices = [MagicMock(message=MagicMock(content="Sorry, I can't make flashcards from this."))]
    client = MagicMock()
    client.chat.completions.create.return_value = reply
    with patch.object(fs, "client", client):
        try:
            fs.generate_flashcards("Some text about cells.", count=3)
        except ss.AIGenerationError as e:
            assert str(e) == "The AI returned flashcards in an unexpected format. Please try again."
        else:
            raise AssertionError("expected AIGenerationError")


def test_flashcard_route_message_reads_well():
    doc = MagicMock(id=3, content="Text.", source_type="pdf", source_url=None)
    doc.filename = "notes.pdf"
    db = MagicMock()
    db.query.side_effect = lambda model: MagicMock(**{
        "filter.return_value.first.return_value": doc if model is Document else None,
        "filter.return_value.order_by.return_value.all.return_value": [] if model is Chunk else [],
    })
    with patch.object(fs, "client", failing_client(status_error(402))):
        try:
            study.create_flashcards(3, count=5, db=db, user=TEST_USER)
        except HTTPException as e:
            assert e.status_code == 502
            assert e.detail == ("The AI service is out of credits. Add credits at openrouter.ai to generate "
                                "summaries, flashcards and answers. Your existing flashcards were not changed."), e.detail
        else:
            raise AssertionError("expected HTTPException")


def test_search_returns_an_error_instead_of_an_error_answer():
    with patch.object(search_service, "client", failing_client(status_error(402))), \
         patch.object(search_route, "search_similar_chunks", return_value=[(0.9, "text", "doc", None, "pdf", None, "p. 1")]):
        try:
            search_route.search(query="What is ATP?", user=TEST_USER)
        except HTTPException as e:
            assert e.status_code == 502 and "out of credits" in e.detail, e.detail
            assert_plain(e.detail)
        else:
            raise AssertionError("search should fail with a plain message, not answer 'ERROR: ...'")


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
