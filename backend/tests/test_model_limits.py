"""Offline checks that no AI call asks for more output than the model allows (OpenRouter's
model list via an httpx mock transport, mocked LLM; no network).

Run from backend/:  .venv/Scripts/python.exe tests/test_model_limits.py
"""
import json
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
os.environ.setdefault("OPENROUTER_API_KEY", "offline-test-key")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"

import httpx

from app.services.ai import flashcard_service as fs
from app.services.ai import merged_service as mg
from app.services.ai import model_limits as ml
from app.services.ai import summary_service as ss

MODELS = {"data": [
    {"id": "openai/gpt-3.5-turbo", "context_length": 16385, "top_provider": {"max_completion_tokens": 4096}},
    {"id": "openai/gpt-4o-mini", "context_length": 128000, "top_provider": {"max_completion_tokens": 16384}},
    {"id": "some/model:free", "context_length": 262144, "top_provider": {"max_completion_tokens": None}},
]}


def listing(body=MODELS, status=200, error=None):
    calls = []

    def handler(request):
        calls.append(request)
        if error:
            raise error
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def load(model, **kw):
    client, calls = listing(**kw)
    with patch.object(ml, "logger"):
        limits = ml.load_model_limits(model, client=client)
    return limits, calls


def reset():
    ml._limits.update(model=None, context=None, max_output=None)


def test_limits_come_from_openrouters_public_list():
    limits, calls = load("openai/gpt-3.5-turbo")
    assert (calls[0].method, str(calls[0].url)) == ("GET", ml.MODELS_URL)
    assert "authorization" not in calls[0].headers, "the list is public; the API key isn't sent"
    assert (limits["context"], limits["max_output"]) == (16385, 4096)
    assert ml.cap_tokens(4500) == 4096 and ml.cap_tokens(3400) == 3400
    load("openai/gpt-4o-mini")
    assert ml.cap_tokens(4500) == 4500 and ml.context_tokens() == 128000
    reset()


def test_unknown_or_unreachable_falls_back_safely():
    for kw, model in [({}, "not/listed"), ({"status": 503}, "openai/gpt-4o-mini"),
                      ({"error": httpx.ConnectError("offline")}, "openai/gpt-4o-mini"),
                      ({"body": "not json"}, "openai/gpt-4o-mini")]:
        load("openai/gpt-4o-mini")  # a previous success must not linger
        limits, _ = load(model, **kw)
        assert (limits["context"], limits["max_output"]) == (None, None), kw
        assert ml.cap_tokens(10_000) == ml.FALLBACK_MAX_OUTPUT == 4096
    reset()


def test_a_model_without_an_output_limit_uses_the_fallback():
    limits, _ = load("some/model:free")
    assert limits["context"] == 262144 and ml.cap_tokens(9000) == 4096
    reset()


def test_nothing_loaded_means_the_fallback_cap():
    reset()
    assert ml.cap_tokens(4500) == 4096 and ml.context_tokens() is None


def reply(text):
    return MagicMock(choices=[MagicMock(finish_reason="stop", message=MagicMock(content=text))])


def test_gpt_35_calls_never_ask_for_more_than_4096():
    load("openai/gpt-3.5-turbo")
    try:
        llm = MagicMock()
        llm.chat.completions.create.return_value = reply("- A point [S0]")
        with patch.object(ss, "client", llm):
            mg.generate_merged_summary([
                mg.MergedSource(1, "a.pdf", "pdf", None, ["Some text."], [("p. 1", None)], document_id=1),
                mg.MergedSource(2, "b.pdf", "pdf", None, ["More text."], [("p. 1", None)], document_id=2),
            ])
            ss.generate_summary("Sentence about cells. " * 400)
        asked = [c.kwargs["max_tokens"] for c in llm.chat.completions.create.call_args_list]
        assert max(asked) == 4096 and all(t <= 4096 for t in asked), asked

        cards = MagicMock()
        cards.chat.completions.create.return_value = reply(json.dumps([{"question": "Q?", "answer": "A"}]))
        with patch.object(fs, "client", cards):
            fs.generate_flashcards("Text.", count=1)
        assert cards.chat.completions.create.call_args.kwargs["max_tokens"] == 4096, "was 4200 before the cap"
    finally:
        reset()


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
