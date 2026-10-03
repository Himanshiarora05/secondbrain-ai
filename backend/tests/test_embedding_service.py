"""Offline checks for app/services/embedding_service.py: nothing heavy at import,
one model load even when the first requests arrive together, and the settings
that keep memory low. fastembed's model is replaced by a fake (no download).

Run from backend/:  .venv/Scripts/python.exe tests/test_embedding_service.py
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database or model hub.
os.environ["DATABASE_URL"] = "postgresql://offline:offline@127.0.0.1:1/offline"
os.environ["HF_HUB_OFFLINE"] = "1"

import numpy as np

from app.services import embedding_service as es


class FakeModel:
    loads = 0
    calls = []

    def __init__(self, model_name, **kwargs):
        time.sleep(0.05)  # slow enough for concurrent first calls to overlap
        FakeModel.loads += 1
        self.model_name, self.kwargs = model_name, kwargs

    def embed(self, texts, batch_size):
        FakeModel.calls.append((list(texts), batch_size))
        return (np.full(es.EMBEDDING_DIM, i, dtype=np.float32) for i, _ in enumerate(texts))


def fresh_fake():
    FakeModel.loads, FakeModel.calls = 0, []
    es._model = None
    import fastembed
    return patch.object(fastembed, "TextEmbedding", FakeModel)


def test_importing_the_app_loads_no_model_libraries():
    # A separate interpreter, so this process's imports don't count.
    code = ("import sys, main; heavy = [m for m in ('fastembed', 'onnxruntime', 'torch', 'chromadb', "
            "'sentence_transformers', 'transformers') if m in sys.modules]; print(heavy)")
    env = {**os.environ, "DATABASE_URL": "postgresql://offline:offline@127.0.0.1:1/offline"}
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "[]", out.stdout


def test_model_is_loaded_once_with_low_memory_settings():
    with fresh_fake():
        threads = [threading.Thread(target=es.get_embeddings, args=(["a", "b"],)) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert FakeModel.loads == 1, FakeModel.loads
        model = es._get_model()
        assert model.model_name == "sentence-transformers/all-MiniLM-L6-v2"
        assert model.kwargs == {"threads": 1, "enable_cpu_mem_arena": False}, model.kwargs
        assert {batch for _, batch in FakeModel.calls} == {es.BATCH_SIZE}


def test_vectors_are_plain_lists_in_order():
    with fresh_fake():
        vectors = es.get_embeddings(["x", "y", "z"])
        assert [v[0] for v in vectors] == [0.0, 1.0, 2.0] and all(isinstance(v, list) for v in vectors)
        assert len(es.get_embedding("q")) == es.EMBEDDING_DIM
        assert es.get_embeddings([]) == []
        assert len(FakeModel.calls) == 2, "an empty list doesn't call the model"


def test_embedding_threads_setting():
    for value, expected in [("", 1), ("4", 4), ("0", 1), ("lots", 1)]:
        with patch.dict(os.environ, {"EMBEDDING_THREADS": value}):
            assert es._threads() == expected, (value, es._threads())


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
