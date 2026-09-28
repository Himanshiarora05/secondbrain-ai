"""
One-time migration: existing Postgres schema -> new Document/Chunk models.

WHY THIS SCRIPT EXISTS
-----------------------
Base.metadata.create_all() (called from init_db() on startup) ONLY creates
tables that don't exist yet. It never ALTERs an existing table, so on a
database that already has a `chunks` table from before this refactor:

  - The new `chroma_id` column will NOT be added automatically.
  - Any old `embedding` column will NOT be removed automatically.
  - The app will start fine, but the first PDF upload will fail with
    something like: psycopg2.errors.UndefinedColumn: column "chroma_id"
    of relation "chunks" does not exist.

This script is the safe path: it inspects the live schema first (it does
not assume column names), adds what's missing, migrates any existing
embeddings into Chroma so old documents stay searchable, and leaves the
legacy embedding column in place until you've verified the migration and
choose to drop it yourself.

USAGE
-----
1. Back up your database first:
     pg_dump "$DATABASE_URL" > backup_before_migration.sql

2. Dry run (default) - reports what it *would* do, changes nothing:
     python scripts/migrate_chunks_to_chroma.py

3. Apply it:
     python scripts/migrate_chunks_to_chroma.py --apply

4. Only after confirming search works on old documents, drop the legacy
   column yourself (this script will print the exact command to run -
   it will NOT drop columns for you):
     ALTER TABLE chunks DROP COLUMN embedding;
"""

import argparse
import json
import sys

from sqlalchemy import inspect, text

sys.path.insert(0, ".")  # allow running from backend/ as `python scripts/...`

from app.database.db import engine, SessionLocal  # noqa: E402
from app.database.chroma import get_collection  # noqa: E402


LEGACY_EMBEDDING_CANDIDATES = ("embedding", "embeddings", "vector")


def inspect_chunks_table():
    insp = inspect(engine)
    if "chunks" not in insp.get_table_names():
        print("No `chunks` table exists yet - nothing to migrate. "
              "init_db() will create the fresh schema on next app startup.")
        return None

    columns = {c["name"]: c for c in insp.get_columns("chunks")}
    print(f"Found existing `chunks` table with columns: {list(columns)}")

    legacy_col = next((c for c in LEGACY_EMBEDDING_CANDIDATES if c in columns), None)
    has_chroma_id = "chroma_id" in columns

    return {
        "columns": columns,
        "legacy_embedding_column": legacy_col,
        "has_chroma_id": has_chroma_id,
    }


def add_chroma_id_column(apply: bool):
    stmt = "ALTER TABLE chunks ADD COLUMN chroma_id VARCHAR;"
    idx_stmt = "CREATE UNIQUE INDEX ix_chunks_chroma_id ON chunks (chroma_id);"
    print(f"[{'APPLY' if apply else 'DRY RUN'}] {stmt}")
    print(f"[{'APPLY' if apply else 'DRY RUN'}] {idx_stmt}")
    if apply:
        with engine.begin() as conn:
            conn.execute(text(stmt))
            conn.execute(text(idx_stmt))


def backfill_embeddings(legacy_col: str, apply: bool):
    """Read each chunk's legacy embedding, push it into Chroma, and set
    chroma_id - without recomputing anything, so this works even if the
    embedding model changed or is unavailable at migration time."""
    session = SessionLocal()
    collection = get_collection()

    rows = session.execute(
        text(f"SELECT id, document_id, content, {legacy_col} FROM chunks")
    ).fetchall()
    print(f"Found {len(rows)} existing chunk rows to backfill.")

    migrated, skipped = 0, 0
    for row in rows:
        chunk_id, document_id, content, raw_embedding = row
        if raw_embedding is None:
            skipped += 1
            continue

        try:
            embedding = (
                json.loads(raw_embedding)
                if isinstance(raw_embedding, str)
                else list(raw_embedding)
            )
        except (TypeError, ValueError):
            print(f"  ! chunk {chunk_id}: could not parse embedding, skipping")
            skipped += 1
            continue

        chroma_id = f"{document_id}-{chunk_id}"

        if apply:
            collection.add(
                ids=[chroma_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[{"document_id": document_id, "chunk_id": chunk_id}],
            )
            session.execute(
                text("UPDATE chunks SET chroma_id = :cid WHERE id = :id"),
                {"cid": chroma_id, "id": chunk_id},
            )
        migrated += 1

    if apply:
        session.commit()
    session.close()

    print(f"{'Migrated' if apply else 'Would migrate'} {migrated} chunks "
          f"into Chroma, skipped {skipped} with no embedding.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                         help="Actually run the migration. Without this flag, "
                              "the script only prints what it would do.")
    args = parser.parse_args()

    info = inspect_chunks_table()
    if info is None:
        return

    if info["has_chroma_id"]:
        print("`chroma_id` column already present - schema already migrated.")
    else:
        add_chroma_id_column(apply=args.apply)

    legacy_col = info["legacy_embedding_column"]
    if legacy_col:
        print(f"Legacy embedding column detected: `{legacy_col}`")
        backfill_embeddings(legacy_col, apply=args.apply)
        print(
            "\nOnce you've confirmed search returns correct results for your "
            "old documents, you can drop the legacy column yourself with:\n"
            f"  ALTER TABLE chunks DROP COLUMN {legacy_col};"
        )
    else:
        print("No legacy embedding column found - nothing to backfill.")

    if not args.apply:
        print("\nThis was a DRY RUN. Re-run with --apply to make these changes.")


if __name__ == "__main__":
    main()
