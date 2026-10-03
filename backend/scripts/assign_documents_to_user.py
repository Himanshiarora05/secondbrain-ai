"""
Give documents and merged sets from before user accounts to an account.

WHY THIS SCRIPT EXISTS
-----------------------
Since accounts were added, every endpoint only sees the signed-in user's
documents (documents.user_id), and search only looks at chunks of those
documents. Documents uploaded before then have no owner, so they're invisible
to everyone until they're assigned to an account.

WHAT IT CHANGES
---------------
For every document with no owner: documents.user_id. For every merged set
with no owner: merged_sets.user_id (skipped if a member belongs to someone
else). Their chunks, search vectors, summaries and flashcards follow their
document. Documents and sets
that already have an owner are never touched, so running it again is safe.

SAFETY
------
One transaction per document, under a row lock: it is either assigned or
left exactly as it was.

USAGE (from backend/, after signing up in the app)
---------------------------------------------------
  Dry run (default) - reports what it would do, changes nothing:
    .venv/Scripts/python.exe scripts/assign_documents_to_user.py --email you@example.com
  Apply:
    .venv/Scripts/python.exe scripts/assign_documents_to_user.py --email you@example.com --apply
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def find_user(db, email: str):
    from app.models.user import User
    from app.services.auth_service import normalize_email
    return db.query(User).filter(User.email == normalize_email(email)).first()


def plan(db) -> dict:
    """What an assignment would change: unowned documents (with their vector
    counts) and unowned merged sets, split into ones that can be assigned and
    ones that can't (a member document belongs to someone else)."""
    from app.models.chunk import Chunk, ChunkEmbedding
    from app.models.document import Document
    from app.models.merged_set import MergedSet, MergedSetDocument

    docs = []
    for doc in db.query(Document).filter(Document.user_id.is_(None)).order_by(Document.id.asc()):
        chunks = db.query(Chunk.id).filter(Chunk.document_id == doc.id).count()
        vectors = (db.query(ChunkEmbedding.chunk_id).join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
                   .filter(Chunk.document_id == doc.id).count())
        docs.append({"id": doc.id, "name": doc.filename, "chunks": chunks, "vectors": vectors})

    sets, blocked = [], []
    for merged in db.query(MergedSet).filter(MergedSet.user_id.is_(None)).order_by(MergedSet.id.asc()):
        owners = {
            row.user_id for row in
            db.query(Document.user_id).join(MergedSetDocument, MergedSetDocument.document_id == Document.id)
            .filter(MergedSetDocument.set_id == merged.id).all()
        }
        entry = {"id": merged.id, "name": merged.name}
        # Assignable if every member is unowned (it will get the same owner) - or it has no members left.
        (sets if owners <= {None} else blocked).append(entry)
    return {"documents": docs, "sets": sets, "blocked_sets": blocked}


def assign_document(db, document_id: int, user_id: int) -> bool:
    """Give one unowned document to user_id. Returns False if it already has an owner.

    Leaves the document unchanged if anything fails.
    """
    from app.models.document import Document

    doc = db.query(Document).filter(Document.id == document_id, Document.user_id.is_(None)).with_for_update().first()
    if doc is None:
        db.rollback()
        return False  # already assigned (e.g. a second run racing this one)
    try:
        doc.user_id = user_id
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


def assign_set(db, set_id: int, user_id: int) -> None:
    from app.models.merged_set import MergedSet
    merged = db.query(MergedSet).filter(MergedSet.id == set_id, MergedSet.user_id.is_(None)).first()
    if merged is not None:
        merged.user_id = user_id
        db.commit()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Give documents and merged sets from before accounts to an account.")
    parser.add_argument("--email", required=True, help="email of the account that gets them (sign up in the app first)")
    parser.add_argument("--apply", action="store_true", help="make the changes (default: dry run)")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    from app.database.db import SessionLocal

    db = SessionLocal()
    try:
        user = find_user(db, args.email)
        if user is None:
            print(f"No account with the email {args.email!r}. Sign up in the app first, then run this again.")
            return 2
        todo = plan(db)

        print(f"{'APPLY' if args.apply else 'DRY RUN'}: assign to #{user.id} {user.email}\n")
        print(f"  {len(todo['documents'])} document(s) without an owner:")
        for d in todo["documents"]:
            print(f"    #{d['id']:<4} {d['name'][:44]:<44} {d['chunks']:>3} chunks, {d['vectors']:>3} search vectors")
        print(f"  {len(todo['sets'])} merged set(s) without an owner:")
        for s in todo["sets"]:
            print(f"    #{s['id']:<4} {s['name'][:60]}")
        for s in todo["blocked_sets"]:
            print(f"    #{s['id']:<4} {s['name'][:60]}  (skipped: a document in it belongs to another account)")

        if not todo["documents"] and not todo["sets"]:
            print("\nNothing to do.")
            return 0
        if not args.apply:
            print("\nRun again with --apply to assign them.")
            return 0

        done, vectors, failed = 0, 0, 0
        for d in todo["documents"]:
            try:
                if assign_document(db, d["id"], user.id):
                    done += 1
                    vectors += d["vectors"]
            except Exception as e:
                failed += 1
                print(f"  FAILED #{d['id']}, left unchanged: {e}")
        for s in todo["sets"]:
            assign_set(db, s["id"], user.id)
        print(f"\nDone: {done} document(s) ({vectors} search vectors) and {len(todo['sets'])} merged set(s) "
              f"assigned to {user.email}, {failed} failed.")
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
