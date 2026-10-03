"""A throwaway Postgres with pgvector for offline tests.

Search vectors live in pgvector, which SQLite can't stand in for, so tests that
store or search vectors run against a private Postgres server that pgserver
starts from a temporary folder (no Docker, no install, no network; it is
deleted when the test ends). It is a test-only dependency:

    .venv/Scripts/python.exe -m pip install -r requirements-dev.txt

Each pg_engine() call is a new, empty database with the vector extension and
every table (or nothing at all, with create_tables=False), so tests don't see
each other's rows.
"""
import atexit
import hashlib
import math
import sys
import tempfile
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import close_all_sessions

from app.database.db import Base
from app.services.embedding_service import EMBEDDING_DIM

_server = None


def pg_engine(create_tables=True):
    global _server
    try:
        import pgserver
    except ImportError:
        sys.exit("This test needs an embedded Postgres with pgvector. Install the test dependencies:\n"
                 "  .venv/Scripts/python.exe -m pip install -r requirements-dev.txt")
    if _server is None:
        _server = pgserver.get_server(tempfile.mkdtemp(prefix="sb-test-pg-"), cleanup_mode="delete")
    name = f"t_{uuid.uuid4().hex[:12]}"
    _server.psql(f"CREATE DATABASE {name};")
    engine = create_engine(_server.get_uri(name))
    # Close sessions tests left open and pooled connections before the server
    # stops (atexit runs last-registered first, and the server registered first).
    atexit.register(_close, engine)
    if create_tables:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        import app.models  # noqa: F401  (registers every table on Base)
        Base.metadata.create_all(engine)
    return engine


def _close(engine):
    close_all_sessions()
    engine.dispose()


def fake_embedding(seed: str) -> list[float]:
    """A deterministic unit vector of the model's size for `seed`."""
    raw = [b - 127.5 for b in hashlib.sha256(seed.encode()).digest()] * (EMBEDDING_DIM // 32)
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def fake_embeddings(texts):
    return [fake_embedding(t) for t in texts]


def axis_vector(i: int, weight: float = 1.0, other: int | None = None) -> list[float]:
    """A vector pointing mostly along axis i (optionally partly along `other`),
    for tests that need a known nearest-neighbour order."""
    v = [0.0] * EMBEDDING_DIM
    v[i] = weight
    if other is not None:
        v[other] = math.sqrt(max(0.0, 1 - weight * weight))
    return v
