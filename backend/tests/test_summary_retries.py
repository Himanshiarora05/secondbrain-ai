"""Offline checks that summary AI calls retry temporary failures, and only those (mocked LLM, no DB).

Run from backend/:  .venv/Scripts/python.exe tests/test_summary_retries.py
"""
import os
import sys
import threading
import tempfile
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

import httpx
import openai

from app.services.ai import summary_service as ss
from app.services.ai import merged_service as mg
from app.services.ai.merged_service import MergedSource

REQ = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def status_error(code):
    return openai.APIStatusError(f"Error code: {code}", response=httpx.Response(code, request=REQ), body=None)


def reply(text):
    return MagicMock(choices=[MagicMock(finish_reason="stop", message=MagicMock(content=text))])


def overloaded_in_body():
    """OpenRouter's 200-with-error reply (see check_reply)."""
    return MagicMock(choices=None, error={"message": "Upstream error from Nvidia: Service temporarily overloaded", "code": 503})


def client_with(*outcomes):
    """Each call takes the next outcome: an exception is raised, anything else is returned."""
    client = MagicMock()
    client.chat.completions.create.side_effect = list(outcomes)
    return client


def summarize(client):
    with patch.object(ss, "client", client), patch.object(ss, "RETRY_DELAY_SECONDS", 0), patch.object(ss, "logger"):
        try:
            return ss.generate_summary("Short text about mitochondria.")
        except ss.AIGenerationError as e:
            return e


def test_temporary_failures_are_retried():
    for first in (status_error(503), status_error(429), status_error(500), overloaded_in_body(),
                  openai.APITimeoutError(request=REQ), openai.APIConnectionError(request=REQ)):
        client = client_with(first, reply("- Mitochondria make ATP."))
        assert summarize(client) == "- Mitochondria make ATP.", type(first).__name__
        assert client.chat.completions.create.call_count == 2


def test_gives_up_after_two_retries_with_the_plain_message():
    client = client_with(status_error(429), status_error(429), status_error(429), reply("never reached"))
    res = summarize(client)
    assert isinstance(res, ss.AIGenerationError) and "rate limit" in str(res), res
    assert client.chat.completions.create.call_count == 3


def test_key_credit_and_other_errors_are_not_retried():
    for exc, text in [(status_error(402), "out of credits"), (status_error(401), "API key"),
                      (status_error(404), "model isn't available"), (status_error(400), "couldn't complete"),
                      (RuntimeError("odd"), "couldn't complete")]:
        client = client_with(exc, reply("never reached"))
        res = summarize(client)
        assert isinstance(res, ss.AIGenerationError) and text in str(res), (exc, res)
        assert client.chat.completions.create.call_count == 1, exc


DAILY = ("{'error': {'message': 'Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model "
         "requests per day', 'code': 429, 'metadata': {'limit_source': 'openrouter_free_tier_daily'}}}")


def daily_limit():
    return openai.APIStatusError(f"Error code: 429 - {DAILY}", response=httpx.Response(429, request=REQ), body=None)


def test_the_daily_free_limit_is_not_retried_and_says_so():
    assert ss.is_daily_limit(daily_limit()) and not ss.is_daily_limit(status_error(429))
    client = client_with(daily_limit(), reply("never reached"))
    res = summarize(client)
    assert isinstance(res, ss.AIGenerationError) and str(res) == ss.DAILY_LIMIT_MESSAGE, res
    assert "free-models-per-day" not in str(res) and "busy right now" not in str(res)
    assert client.chat.completions.create.call_count == 1

    from app.services.ai import flashcard_service as fs
    client = client_with(daily_limit(), reply("never reached"))
    with patch.object(fs, "client", client), patch.object(ss, "logger"):
        try:
            fs.generate_flashcards("Some text.", count=3)
            raise AssertionError("expected AIGenerationError")
        except ss.AIGenerationError as e:
            assert str(e) == ss.DAILY_LIMIT_MESSAGE
    assert client.chat.completions.create.call_count == 1, "flashcards don't retry it either"


def test_empty_reply_is_not_retried():
    client = client_with(reply(""), reply("never reached"))
    res = summarize(client)
    assert isinstance(res, ss.AIGenerationError) and "empty reply" in str(res)
    assert client.chat.completions.create.call_count == 1


def test_waits_a_little_longer_each_time():
    client = client_with(status_error(503), status_error(503), reply("ok"))
    with patch.object(ss, "client", client), patch.object(ss.time, "sleep") as sleep, patch.object(ss, "logger"):
        assert ss.generate_summary("Short text.") == "ok"
    assert [c.args[0] for c in sleep.call_args_list] == [ss.RETRY_DELAY_SECONDS, 2 * ss.RETRY_DELAY_SECONDS]


def test_a_merged_summary_survives_one_overloaded_call():
    long_source = MergedSource(1, "big.pdf", "pdf", None, [f"Chunk {i}. " + "x" * 900 for i in range(8)],
                               [(f"p. {i + 1}", None) for i in range(8)], document_id=1)
    small = MergedSource(2, "small.pptx", "pptx", None, ["[Slide 1] Short."], [("Slide 1", None)], document_id=2)
    calls = []
    lock = threading.Lock()

    def answer(**kw):
        # Map calls run in parallel, so pick the overloaded one by content, not by order.
        user = kw["messages"][1]["content"]
        with lock:
            calls.append(user)
            first_try = calls.count(user) == 1
        if "[S0] Chunk 0." in user and first_try:
            return overloaded_in_body()  # the map call for the first batch hits an overloaded provider
        if kw["messages"][0]["content"].startswith("You are an expert study assistant creating one"):
            return reply("- Point [S0][S8]")
        return reply("- note [S0]")

    client = MagicMock()
    client.chat.completions.create.side_effect = answer
    with patch.object(ss, "client", client), patch.object(ss, "RETRY_DELAY_SECONDS", 0), patch.object(ss, "logger"):
        out = mg.generate_merged_summary([long_source, small])
    assert out.endswith("- Point (1: p. 1; 2: Slide 1)"), out
    first_batch = [c for c in calls if "[S0] Chunk 0." in c]
    assert len(first_batch) == 2 and first_batch[0] == first_batch[1], "the failed call was retried as is"


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
