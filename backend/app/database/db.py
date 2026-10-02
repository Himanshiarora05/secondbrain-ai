"""
Database engine + session setup.

IMPORTANT: This file used to also define the Document/Chunk ORM models
directly, while app/models/document.py and app/models/chunk.py defined a
*second*, slightly different copy of the same two classes (mapped to the
same table names). That's a landmine: depending on import order you could
silently get the wrong columns. Document/Chunk now live in app/models/
ONLY. This file just owns the engine/session/Base.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env and fill in your "
        "real Postgres connection string - no default credentials are baked "
        "into the app."
    )

# echo=True is noisy in production logs; only echo when explicitly asked.
# Hosted Postgres (Neon) closes idle connections and suspends the database, so
# check a pooled connection before using it and replace old ones.
engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    pool_pre_ping=True,
    pool_recycle=300,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create tables for all models registered on Base and run column migrations.

    Must be called AFTER the model modules (app.models.document,
    app.models.chunk, summary, flashcard) have been imported at least once,
    otherwise SQLAlchemy won't know about their tables yet.
    """
    from sqlalchemy import text
    from app.models import document, chunk, summary, flashcard, merged_set, user, quiz  # noqa: F401  (registers models on Base)
    Base.metadata.create_all(bind=engine)

    # Database-level migrations for multi-source ingestion with explicit defaults
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_type VARCHAR DEFAULT 'pdf' NOT NULL;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_url VARCHAR;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS metadata_json TEXT;"
            )
        )
        conn.execute(
            text(
                "UPDATE documents SET source_type = 'pdf' WHERE source_type IS NULL;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS start_seconds INTEGER;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS page_start INTEGER;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS page_end INTEGER;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE flashcards ADD COLUMN IF NOT EXISTS source_label VARCHAR;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE flashcards ADD COLUMN IF NOT EXISTS source_url VARCHAR;"
            )
        )
        # Spaced repetition (SM-2) state on both kinds of card; see ReviewScheduleMixin.
        for table in ("flashcards", "merged_flashcards"):
            for column in (
                "ease DOUBLE PRECISION DEFAULT 2.5 NOT NULL",
                "interval_days INTEGER DEFAULT 0 NOT NULL",
                "repetitions INTEGER DEFAULT 0 NOT NULL",
                "due_date DATE",
                "last_reviewed_at TIMESTAMP",
                "first_reviewed_on DATE",
            ):
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column};"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_due_date ON {table} (due_date);"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_first_reviewed_on ON {table} (first_reviewed_on);"))
        # Ownership (user accounts). Existing rows stay null until
        # scripts/assign_documents_to_user.py assigns them.
        for table in ("documents", "merged_sets"):
            conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);"
            ))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_user_id ON {table} (user_id);"))
