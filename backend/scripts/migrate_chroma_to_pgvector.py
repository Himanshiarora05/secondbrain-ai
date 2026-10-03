"""
Move search vectors from the old local Chroma store into pgvector.

WHY THIS SCRIPT EXISTS
-----------------------
Search vectors used to live in Chroma (`vector_db/`, collection
`secondbrain_chunks`, one vector per chunk with id "{document_id}-{index}",
stored on the chunk as `chunks.chroma_id`). They now live in Postgres, in
`chunk_embeddings` (one row per chunk, pgvector). This copies each Chroma
vector onto its chunk, so existing documents stay searchable without
re-embedding anything.

WHAT IT CHANGES
---------------
Only inserts into `chunk_embeddings` (and creates it, with the `vector`
extension, if missing - the same as the backend does on startup). A Chroma
vector is matched to its chunk by `chunks.chroma_id`, or failing that by its
metadata (`document_id` + `chunk_index`, the chunk's position in its
document). Chunks that already have a vector are left alone, so running it
again is safe. Chroma is only read.

Vectors with no chunk (their document was deleted) are reported and skipped.
Chunks with no vector are reported; `--embed-missing` embeds them with the
app's model (the vectors are the same as Chroma's, all-MiniLM-L6-v2).

REQUIREMENTS
------------
chromadb is no longer a dependency of the app; install it just for this:
    .venv/Scripts/python.exe -m pip install chromadb
(Or skip Chroma altogether with --skip-chroma: every chunk is embedded from
its text instead, which gives the same vectors but takes a few minutes.)
The target Postgres needs pgvector (Neon has it). To move a local setup to
Neon: restore your database there first (docs/DEPLOY.md), then point this
script at Neon with --database-url and at your local vector_db/.

USAGE (from backend/)
---------------------
  Dry run (default) - reports what it would do, changes nothing:
    .venv/Scripts/python.exe scripts/migrate_chroma_to_pgvector.py --database-url "postgresql://...neon.tech/neondb?sslmode=require"
  Apply:
    .venv/Scripts/python.exe scripts/migrate_chroma_to_pgvector.py --database-url "..." --apply
  Options: --chroma-dir PATH (default: CHROMA_DIR or vector_db), --embed-missing, --skip-chroma
  Without --database-url, DATABASE_URL from the environment / backend/.env is used.
"""

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

COLLECTION = "secondbrain_chunks"
PAGE_SIZE = 500


def read_chroma(collection, page_size=PAGE_SIZE):
    """Yield (id, embedding as a list, metadata) for every vector in the collection."""
    offset = 0
    while True:
        page = collection.get(include=["embeddings", "metadatas"], limit=page_size, offset=offset)
        ids = page["ids"]
        if not ids:
            return
        for vid, emb, meta in zip(ids, page["embeddings"], page["metadatas"]):
            yield vid, [float(x) for x in emb], meta or {}
        offset += len(ids)


def plan(db, vectors, dim):
    """Match Chroma vectors to chunks. Returns a report dict with `rows`
    [(chunk_id, embedding)] to insert and `missing` chunk ids without a vector."""
    from sqlalchemy import inspect
    from app.models.chunk import Chunk, ChunkEmbedding

    by_chroma_id, by_position, all_chunks = {}, {}, set()
    positions = defaultdict(int)
    for chunk_id, document_id, chroma_id in (
        db.query(Chunk.id, Chunk.document_id, Chunk.chroma_id).order_by(Chunk.document_id, Chunk.id)
    ):
        all_chunks.add(chunk_id)
        if chroma_id:
            by_chroma_id[chroma_id] = chunk_id
        by_position[(document_id, positions[document_id])] = chunk_id
        positions[document_id] += 1
    # A dry run against a database the backend hasn't started on yet has no table.
    have = ({row[0] for row in db.query(ChunkEmbedding.chunk_id)}
            if inspect(db.get_bind()).has_table(ChunkEmbedding.__tablename__) else set())

    report = {"vectors": 0, "rows": [], "already": 0, "orphans": [], "bad_dim": [], "duplicates": 0}
    taken = set()
    for vid, emb, meta in vectors:
        report["vectors"] += 1
        chunk_id = by_chroma_id.get(vid)
        if chunk_id is None and meta.get("document_id") is not None and meta.get("chunk_index") is not None:
            chunk_id = by_position.get((int(meta["document_id"]), int(meta["chunk_index"])))
        if chunk_id is None:
            report["orphans"].append(vid)
        elif len(emb) != dim:
            report["bad_dim"].append(vid)
        elif chunk_id in have:
            report["already"] += 1
        elif chunk_id in taken:
            report["duplicates"] += 1
        else:
            taken.add(chunk_id)
            report["rows"].append((chunk_id, emb))
    report["missing"] = sorted(all_chunks - have - taken)
    report["chunks"] = len(all_chunks)
    return report


def insert(db, rows, batch=PAGE_SIZE):
    from app.models.chunk import ChunkEmbedding

    for start in range(0, len(rows), batch):
        db.add_all([ChunkEmbedding(chunk_id=cid, embedding=emb) for cid, emb in rows[start:start + batch]])
        db.commit()


def embed_missing(db, chunk_ids, embed, batch=64):
    from app.models.chunk import Chunk

    for start in range(0, len(chunk_ids), batch):
        ids = chunk_ids[start:start + batch]
        chunks = db.query(Chunk.id, Chunk.content).filter(Chunk.id.in_(ids)).order_by(Chunk.id).all()
        vectors = embed([c.content or "" for c in chunks])
        insert(db, [(c.id, v) for c, v in zip(chunks, vectors)])
    return len(chunk_ids)


def open_collection(chroma_dir):
    try:
        import chromadb
    except ImportError:
        sys.exit("chromadb isn't installed (it is no longer an app dependency). Install it for this script:\n"
                 "  .venv/Scripts/python.exe -m pip install chromadb")
    if not Path(chroma_dir).exists():
        sys.exit(f"No Chroma store at {Path(chroma_dir).resolve()} (use --chroma-dir).")
    client = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        return client.get_collection(COLLECTION)
    except Exception:
        sys.exit(f"The Chroma store at {chroma_dir} has no collection {COLLECTION!r}.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Copy search vectors from local Chroma into pgvector.")
    parser.add_argument("--apply", action="store_true", help="make the changes (default: dry run)")
    parser.add_argument("--database-url", help="target Postgres (default: DATABASE_URL / backend/.env)")
    parser.add_argument("--chroma-dir", help="Chroma folder (default: CHROMA_DIR or vector_db)")
    parser.add_argument("--embed-missing", action="store_true", help="also embed chunks Chroma has no vector for")
    parser.add_argument("--skip-chroma", action="store_true",
                        help="don't read Chroma (no chromadb needed): embed every chunk without a vector from its text")
    args = parser.parse_args(argv)
    if args.skip_chroma:
        args.embed_missing = True

    # The database URL has to be in place before app.database.db is imported.
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    chroma_dir = args.chroma_dir or os.getenv("CHROMA_DIR") or "vector_db"

    from app.database.db import SessionLocal, engine, init_db
    from app.services.embedding_service import EMBEDDING_DIM

    host = engine.url.host or "local socket"
    if args.skip_chroma:
        collection = None
        source = "no Chroma (embedding chunks from their text)"
    else:
        collection = open_collection(chroma_dir)
        source = f"Chroma {Path(chroma_dir).resolve()} ({collection.count()} vectors)"
    print(f"{'APPLY' if args.apply else 'DRY RUN'}: {source} -> Postgres {host}/{engine.url.database}\n")
    if args.apply:
        init_db()  # vector extension + chunk_embeddings, as at backend startup

    db = SessionLocal()
    try:
        report = plan(db, read_chroma(collection) if collection is not None else [], EMBEDDING_DIM)

        print(f"  {report['chunks']} chunks in Postgres, {report['vectors']} vectors in Chroma")
        print(f"  {len(report['rows'])} vectors to copy, {report['already']} chunks already have one")
        if report["orphans"]:
            print(f"  {len(report['orphans'])} vectors match no chunk (deleted documents), skipped: "
                  f"{', '.join(report['orphans'][:10])}{' ...' if len(report['orphans']) > 10 else ''}")
        if report["bad_dim"]:
            print(f"  {len(report['bad_dim'])} vectors aren't {EMBEDDING_DIM}-dimensional, skipped")
        if report["duplicates"]:
            print(f"  {report['duplicates']} extra vectors for an already matched chunk, skipped")
        if report["missing"]:
            what = "will be embedded" if args.embed_missing else "search won't find them; use --embed-missing"
            print(f"  {len(report['missing'])} chunks have no vector ({what})")

        if not args.apply:
            print("\nThis was a DRY RUN. Run again with --apply to copy the vectors.")
            return 0
        insert(db, report["rows"])
        embedded = 0
        if args.embed_missing and report["missing"]:
            from app.services.embedding_service import get_embeddings
            embedded = embed_missing(db, report["missing"], get_embeddings)
        print(f"\nDone: copied {len(report['rows'])} vectors, embedded {embedded} missing.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
