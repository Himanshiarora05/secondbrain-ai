"""
Single source of truth for the embedding model.

Previously this same SentenceTransformer("all-MiniLM-L6-v2") model was
instantiated separately in rag_service.py AND search_service.py (and a
third, unused copy lived in the old version of this file). Loading it
twice roughly doubles startup time and memory for no benefit, since the
model is stateless and thread-safe to share. Everything should import
from here now.
"""

from functools import lru_cache
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def get_embedding(text: str) -> list[float]:
    """Embed a single string."""
    return _get_model().encode(text).tolist()


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings (faster than calling get_embedding in a loop)."""
    return _get_model().encode(texts).tolist()
