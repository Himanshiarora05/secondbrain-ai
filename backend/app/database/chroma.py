"""
Chroma vector store.

Previously this file was empty and app/services/search_service.py instead
loaded EVERY chunk row out of Postgres on every single search request,
decoded its embedding from a JSON string, and computed cosine similarity
by hand in a Python loop. That works fine for a few dozen PDFs but will
get slow (and expensive in memory) once the library grows. Chroma keeps
an on-disk index (HNSW) so lookups stay fast as the collection grows,
and it's already in requirements.txt (was just unused).
"""

import os
import chromadb

CHROMA_DIR = os.getenv("CHROMA_DIR", "vector_db")

_client = chromadb.PersistentClient(path=CHROMA_DIR)

_collection = _client.get_or_create_collection(
    name="secondbrain_chunks",
    metadata={"hnsw:space": "cosine"},
)


def get_collection():
    return _collection
