"""
Single source of truth for the embedding model.

all-MiniLM-L6-v2 (384 dimensions) run through fastembed: the same model as
sentence-transformers' copy, exported to ONNX, so no torch. Its vectors match
sentence-transformers' to within float rounding (both are unit length), so
vectors made by the old setup and moved over by
scripts/migrate_chroma_to_pgvector.py sit in the same space as new ones.

Memory matters on a 512 MB host: nothing heavy is imported until the first
embedding is needed, the model is loaded once (behind a lock, so two first
requests can't load two copies), and texts are embedded in small batches with
ONNX Runtime's memory arena off: the arena keeps its peak allocation for good
(measured: ~190 MB more after embedding 200 chunks), without it memory goes
back down, at the same speed.

The model files are downloaded on first use into FASTEMBED_CACHE_PATH (default:
the system temp folder). Hosts that wipe the disk on restart should download
them at build time instead (`python -m app.services.embedding_service`; see
render.yaml).
"""

import os
import threading

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
# Activation memory grows with batch size x sequence length; 16 keeps a batch
# of full-length chunks small.
BATCH_SIZE = 16

_model = None
_model_lock = threading.Lock()


def _threads():
    """ONNX Runtime threads (EMBEDDING_THREADS; default 1, which suits a small shared CPU)."""
    try:
        return max(1, int(os.getenv("EMBEDDING_THREADS", "").strip()))
    except ValueError:
        return 1


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from fastembed import TextEmbedding
                _model = TextEmbedding(MODEL_NAME, threads=_threads(), enable_cpu_mem_arena=False)
    return _model


def get_embedding(text: str) -> list[float]:
    """Embed a single string."""
    return get_embeddings([text])[0]


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings (faster than calling get_embedding in a loop)."""
    if not texts:
        return []
    return [vector.tolist() for vector in _get_model().embed(list(texts), batch_size=BATCH_SIZE)]


if __name__ == "__main__":
    # Download the model files (build step) and check they load.
    print(f"{MODEL_NAME}: {len(get_embedding('warm up'))} dimensions, "
          f"cache {os.getenv('FASTEMBED_CACHE_PATH') or 'system temp folder'}")
