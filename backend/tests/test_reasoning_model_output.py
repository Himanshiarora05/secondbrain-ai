"""Offline checks for replies from reasoning / Markdown-happy models (mocked LLM, no DB).

Covers escaped citation labels ("\\[S0\\]"), room for reasoning in max_tokens,
the cut-off warning and empty replies.

Run from backend/:  .venv/Scripts/python.exe tests/test_reasoning_model_output.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database, vector store or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-test-key")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"

from fastapi import HTTPException

from types import SimpleNamespace

# The signed-in user the route functions are called for (routes take it from get_current_user).
TEST_USER = SimpleNamespace(id=1)

from app.services.ai import summary_service as ss
from app.services.ai.model_limits import cap_tokens
from app.services.ai import flashcard_service as fs
from app.services import search_service
from app.routes import search as search_route

PAGES = [("p. 1", None), ("pp. 2–3", None), ("p. 4", None)]


def replying_client(text, finish_reason="stop"):
    client = MagicMock()
    choice = MagicMock(finish_reason=finish_reason, message=MagicMock(content=text))
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


def test_escaped_labels_become_citations():
    cases = {
        r"- A graph is a pair (V, E) \[S0\]": "- A graph is a pair (V, E) (p. 1)",
        r"- Degree counts edges \[S0\]\[S1\]": "- Degree counts edges (p. 1; pp. 2–3)",
        r"- Loops \[S1, S2\]": "- Loops (pp. 2–3; p. 4)",
        r"- Mixed [S0] \[S2\]": "- Mixed (p. 1; p. 4)",
        r"- Half escaped \[S1]": "- Half escaped (pp. 2–3)",
        r"- Made-up label \[S9\]": "- Made-up label",
        "- Plain [S2]": "- Plain (p. 4)",
    }
    for text, expected in cases.items():
        got = ss.replace_labels(text, PAGES)
        assert got == expected, (text, got)
        assert "\\" not in got, got


def test_other_escapes_are_left_alone():
    text = r"- Set notation \(V\) and a literal \[not a label\] [S0]"
    assert ss.replace_labels(text, PAGES) == r"- Set notation \(V\) and a literal \[not a label\] (p. 1)"


def test_cited_summary_with_escaped_labels():
    client = replying_client("# Graphs\n- A graph is (V, E) \\[S0\\]\n- Edges join vertices \\[S1\\]\\[S2\\]")
    with patch.object(ss, "client", client):
        out = ss.generate_cited_summary(["chunk 0", "chunk 1", "chunk 2"], PAGES)
    assert out == "# Graphs\n- A graph is (V, E) (p. 1)\n- Edges join vertices (pp. 2–3; p. 4)", out


def test_calls_leave_room_for_reasoning():
    client = replying_client("- Point [S0]")
    with patch.object(ss, "client", client):
        ss.generate_summary("Short text.")
        ss.generate_summary("Sentence about cells. " * 400)  # map + reduce
        ss.generate_cited_summary(["Mitochondria make ATP. " * 200] * 3, PAGES)  # labelled map + final
    caps = {c.kwargs["max_tokens"] for c in client.chat.completions.create.call_args_list}
    assert caps == {cap_tokens(400 + ss.REASONING_ALLOWANCE), cap_tokens(900 + ss.REASONING_ALLOWANCE)}, caps

    client = replying_client('[{"question": "Q?", "answer": "A", "source": "S0"}]')
    with patch.object(fs, "client", client):
        fs.generate_flashcards("Text.", count=1)
    assert client.chat.completions.create.call_args.kwargs["max_tokens"] == cap_tokens(1200 + ss.REASONING_ALLOWANCE)


def test_cut_off_reply_is_logged_but_kept():
    client = replying_client("- A point that stops mid", finish_reason="length")
    with patch.object(ss, "client", client), patch.object(ss, "logger") as log:
        assert ss.generate_summary("Short text.") == "- A point that stops mid"
    assert any("length limit" in str(c) for c in log.warning.call_args_list), log.warning.call_args_list

    client = replying_client('[{"question": "Q?", "answer": "A"}]', finish_reason="length")
    with patch.object(fs, "client", client), patch.object(ss, "logger") as log:
        fs.generate_flashcards("Text.", count=1)
    assert any("generating flashcards" in str(c) for c in log.warning.call_args_list)


def test_empty_reply_has_a_plain_message():
    for content in (None, "", "   \n"):
        with patch.object(ss, "client", replying_client(content, finish_reason="length")), patch.object(ss, "logger"):
            for call in (lambda: ss.generate_summary("Short text."),
                         lambda: ss.generate_cited_summary(["chunk"], PAGES),
                         lambda: ss.generate_summary("Sentence about cells. " * 400)):
                try:
                    call()
                except ss.AIGenerationError as e:
                    assert str(e) == "The AI returned an empty reply. Please try again.", str(e)
                else:
                    raise AssertionError(f"expected AIGenerationError for {content!r}")


def test_empty_reply_logs_the_raw_reply():
    from openai.types.chat import ChatCompletion
    response = ChatCompletion.model_validate({
        "id": "gen-123", "object": "chat.completion", "created": 0, "model": "some/model:free",
        "choices": [{"index": 0, "finish_reason": "length",
                     "message": {"role": "assistant", "content": None, "reasoning": "Let me think about graphs..."}}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 3400, "total_tokens": 4300},
        "provider": "Nvidia",
    })
    client = MagicMock()
    client.chat.completions.create.return_value = response
    with patch.object(ss, "client", client), patch.object(ss, "logger") as log:
        try:
            ss.generate_summary("Short text.")
        except ss.AIGenerationError:
            pass
        else:
            raise AssertionError("expected AIGenerationError")
    logged = " ".join(c.args[0] for c in log.warning.call_args_list)
    for part in ("had no text", "finish_reason 'length'", '"completion_tokens":3400',
                 "Let me think about graphs...", '"provider":"Nvidia"', "gen-123"):
        assert part in logged, (part, logged)

    long = ChatCompletion.model_validate({**response.model_dump(), "provider": "x" * 50_000})
    assert len(ss.raw_reply(long)) < ss.RAW_REPLY_LOG_CHARS + 100
    assert ss.raw_reply(long).endswith("characters in all)")


def test_search_with_empty_reply_is_a_502():
    with patch.object(search_service, "client", replying_client(None)), patch.object(ss, "logger"), \
         patch.object(search_route, "search_similar_chunks", return_value=[(0.9, "text", "doc", None, "pdf", None, "p. 1")]):
        try:
            search_route.search(query="What is a graph?", user=TEST_USER)
        except HTTPException as e:
            assert e.status_code == 502 and e.detail == "The AI returned an empty reply. Please try again.", e.detail
        else:
            raise AssertionError("expected HTTPException")


def test_flashcards_with_empty_reply_keep_their_message():
    with patch.object(fs, "client", replying_client(None)):
        try:
            fs.generate_flashcards("Text.", count=1)
        except ss.AIGenerationError as e:
            assert str(e) == "The AI returned flashcards in an unexpected format. Please try again.", str(e)
        else:
            raise AssertionError("expected AIGenerationError")


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
