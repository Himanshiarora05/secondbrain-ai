"""Offline checks that OPENROUTER_MODEL picks the model for every AI call (mocked LLM, no DB).

Run from backend/:  .venv/Scripts/python.exe tests/test_model_setting.py
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
# Set before the services are imported: they read it once, like the real app.
# The services call load_dotenv(), which doesn't override a variable that's already set.
TEST_MODEL = "example/test-model:free"
os.environ["OPENROUTER_MODEL"] = f"  {TEST_MODEL}  "

from app.services.ai import summary_service as ss
from app.services.ai import flashcard_service as fs
from app.services import search_service


def replying_client(text):
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content=text))])
    return client


def models_used(client):
    return {c.kwargs["model"] for c in client.chat.completions.create.call_args_list}


def test_default_model_when_unset_or_blank():
    for value in (None, "", "   "):
        env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_MODEL"}
        if value is not None:
            env["OPENROUTER_MODEL"] = value
        with patch.dict(os.environ, env, clear=True):
            assert ss.configured_model() == "openai/gpt-4o-mini", repr(value)


def test_setting_overrides_and_is_trimmed():
    assert ss.MODEL_NAME == TEST_MODEL, ss.MODEL_NAME
    assert fs.MODEL_NAME == TEST_MODEL and search_service.MODEL_NAME == TEST_MODEL


def test_summaries_use_the_setting():
    client = replying_client("- Mitochondria make ATP [S0].")
    with patch.object(ss, "client", client):
        ss.generate_summary("Short text about mitochondria.")
        ss.generate_summary("Sentence about cells. " * 400)  # map-reduce: map and reduce calls
        ss.generate_cited_summary(["Mitochondria make ATP."], [("p. 1", None)])
    assert client.chat.completions.create.call_count >= 4
    assert models_used(client) == {TEST_MODEL}, models_used(client)


def test_flashcards_use_the_setting():
    client = replying_client('[{"question": "What makes ATP?", "answer": "Mitochondria", "source": "S0"}]')
    with patch.object(fs, "client", client):
        fs.generate_flashcards("Mitochondria make ATP.", count=1)
        fs.generate_cited_flashcards(["Mitochondria make ATP."], [("p. 1", None)], count=1)
    assert models_used(client) == {TEST_MODEL}, models_used(client)


def test_search_answers_use_the_setting():
    client = replying_client("ATP is made in mitochondria.")
    with patch.object(search_service, "client", client):
        search_service.generate_answer("What makes ATP?", "Mitochondria make ATP.")
    assert models_used(client) == {TEST_MODEL}, models_used(client)


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
