"""Offline checks for OpenRouter errors sent inside an HTTP 200 reply (fake HTTP transport, no network, no DB).

OpenRouter sometimes answers 200 with {"error": {"code": 503, ...}} and no choices.
These run the real openai SDK against a mock transport so the reply is parsed
exactly as in the app.

Run from backend/:  .venv/Scripts/python.exe tests/test_error_in_reply_body.py
"""
import json
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
os.environ.setdefault("OPENROUTER_API_KEY", "offline-test-key")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"

import httpx
from fastapi import HTTPException
from openai import OpenAI

from app.services.ai import summary_service as ss

ss.RETRY_DELAY_SECONDS = 0  # overloads are retried; no need to wait in tests
from app.services.ai import flashcard_service as fs
from app.services import search_service
from app.routes import search as search_route

OVERLOADED = {"message": "Upstream error from Nvidia: Service temporarily overloaded", "code": 503,
              "metadata": {"error_type": "provider_overloaded"}}
PAGES = [("p. 1", None), ("p. 2", None)]


def error_body(error):
    return {"id": "gen-1", "choices": None, "created": None, "model": None, "object": None, "usage": None, "error": error}


def ok_body(text):
    return {"id": "gen-2", "object": "chat.completion", "created": 1, "model": "m",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}]}


def sdk_client(*bodies):
    """A real OpenAI client whose HTTP replies are `bodies` in turn (the last repeats), all with status 200."""
    calls = []

    def handler(request):
        body = bodies[min(len(calls), len(bodies) - 1)]
        calls.append(request)
        return httpx.Response(200, json=body)

    client = OpenAI(api_key="k", base_url="https://openrouter.ai/api/v1", max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return client, calls


def expect_message(call, expected):
    try:
        call()
    except ss.AIGenerationError as e:
        assert expected in str(e), str(e)
        assert "Error code" not in str(e) and "Nvidia" not in str(e), f"raw error leaked: {e}"
        return e
    raise AssertionError("expected AIGenerationError")


def test_summaries_explain_an_overloaded_provider():
    client, _ = sdk_client(error_body(OVERLOADED))
    with patch.object(ss, "client", client), patch.object(ss, "logger"):
        for call in (lambda: ss.generate_summary("Short text."),
                     lambda: ss.generate_summary("Sentence about cells. " * 400),
                     lambda: ss.generate_cited_summary(["chunk a", "chunk b"], PAGES)):
            e = expect_message(call, "having problems right now")
            assert e.__cause__ is not None and e.__cause__.status_code == 503, repr(e.__cause__)


def test_status_in_the_body_picks_the_message():
    cases = [
        ({"message": "Rate limit exceeded", "code": 429}, "rate limit"),
        ({"message": "Insufficient credits", "code": 402}, "out of credits"),
        ({"message": "No endpoints found", "code": 404}, "model isn't available"),
        ({"message": "odd", "code": "E_WEIRD"}, "having problems"),  # unusable code -> 502
        (None, "having problems"),                                   # no error and no choices -> 502
    ]
    for error, expected in cases:
        client, _ = sdk_client(error_body(error))
        with patch.object(ss, "client", client), patch.object(ss, "logger"):
            expect_message(lambda: ss.generate_summary("Short text."), expected)


def test_flashcards_retry_an_overload_once():
    client, calls = sdk_client(error_body(OVERLOADED))
    with patch.object(fs, "client", client), patch.object(ss, "logger"):
        expect_message(lambda: fs.generate_flashcards("Text.", count=1), "having problems right now")
    assert len(calls) == 2, len(calls)


def test_flashcards_recover_when_the_retry_works():
    client, calls = sdk_client(error_body(OVERLOADED), ok_body('[{"question": "Q?", "answer": "A"}]'))
    with patch.object(fs, "client", client):
        assert fs.generate_flashcards("Text.", count=1) == [{"question": "Q?", "answer": "A"}]
    assert len(calls) == 2


def test_flashcards_do_not_retry_a_credit_error_in_the_body():
    client, calls = sdk_client(error_body({"message": "Insufficient credits", "code": 402}))
    with patch.object(fs, "client", client), patch.object(ss, "logger"):
        expect_message(lambda: fs.generate_flashcards("Text.", count=1), "out of credits")
    assert len(calls) == 1, len(calls)


def test_search_explains_an_overloaded_provider():
    client, _ = sdk_client(error_body(OVERLOADED))
    with patch.object(search_service, "client", client), patch.object(ss, "logger"), \
         patch.object(search_route, "search_similar_chunks", return_value=[(0.9, "text", "doc", None, "pdf", None, "p. 1")]):
        try:
            search_route.search(query="What is a graph?")
        except HTTPException as e:
            assert e.status_code == 502 and "having problems right now" in e.detail, e.detail
        else:
            raise AssertionError("expected HTTPException")


def test_normal_replies_are_unchanged():
    client, _ = sdk_client(ok_body("- A graph is (V, E) [S0]"))
    with patch.object(ss, "client", client):
        assert ss.generate_cited_summary(["chunk a"], PAGES) == "- A graph is (V, E) (p. 1)"


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
