"""
Re-index PDFs uploaded before page tracking, so they get page citations.

WHY THIS SCRIPT EXISTS
-----------------------
PDFs uploaded before page tracking have chunks without page_start/page_end,
so their summaries, flashcards and search results can't cite "p. 12". The
original files are still in uploads/, so this re-reads each one page by page
and rebuilds its chunks (Postgres) and vectors (Chroma) with page ranges.

WHAT CHANGES / WHAT DOESN'T
---------------------------
- Changes: the document's chunks and search vectors. Chunk boundaries can
  differ slightly from before (sentences are now split per page), which only
  affects search matching.
- Unchanged: the document itself (id, name, full text), its summary and its
  flashcards. They only gain page citations once regenerated (needs AI credits).
- Skipped: PDFs whose chunks already have pages (unless --force), and PDFs
  whose file is missing from uploads/.

SAFETY
------
Per document: the new chunks are embedded first (nothing changed yet); the
old Chroma vectors are read into memory before they're removed; if adding
the new vectors fails, the old ones are put back and the database change is
rolled back, so the document is left exactly as it was.

USAGE (from backend/)
---------------------
  Dry run (default) - reports what it would do, changes nothing:
    .venv/Scripts/python.exe scripts/reindex_pdf_pages.py
  Apply:
    .venv/Scripts/python.exe scripts/reindex_pdf_pages.py --apply
  Only some documents / redo documents that already have pages:
    .venv/Scripts/python.exe scripts/reindex_pdf_pages.py --ids 1 2 --apply --force
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

UPLOAD_DIR = Path("uploads")


def plan_document(db, doc, force=False, upload_dir=UPLOAD_DIR):
    """What re-indexing `doc` would do. Returns (report dict, new chunks or None)."""
    from app.models.chunk import Chunk
    from app.services.pdf.pdf_service import PDFService
    from app.services.rag.rag_service import RAGService

    old = db.query(Chunk).filter(Chunk.document_id == doc.id).order_by(Chunk.id.asc()).all()
    report = {"id": doc.id, "name": doc.filename, "old_chunks": len(old)}
    if old and all(c.page_start is not None for c in old) and not force:
        return {**report, "action": "skip", "reason": "already has page numbers"}, None
    # Its scanned pages were read by OCR at upload; re-extracting would drop that text.
    if '"ocr_pages"' in (getattr(doc, "metadata_json", None) or ""):
        return {**report, "action": "skip", "reason": "has OCR pages"}, None

    path = Path(upload_dir) / f"{doc.file_id}.pdf"
    if not path.exists():
        return {**report, "action": "skip", "reason": f"file missing: {path}"}, None

    try:
        pages = PDFService.extract_pages(str(path))
    except Exception as e:
        return {**report, "action": "skip", "reason": f"can't read PDF: {e}"}, None
    new = RAGService.chunk_pages(pages)
    if not new:
        return {**report, "action": "skip", "reason": "no readable text"}, None

    return {**report, "action": "reindex", "new_chunks": len(new), "pages": len(pages),
            "page_range": (new[0]["page_start"], new[-1]["page_end"])}, new


def apply_document(db, collection, doc, new_chunks, embed):
    """Swap `doc`'s chunks and vectors for `new_chunks`; restores everything on failure."""
    from app.models.chunk import Chunk

    texts = [c["text"] for c in new_chunks]
    embeddings = embed(texts)  # may raise: nothing has changed yet

    old_ids = [c.chroma_id for c in db.query(Chunk).filter(Chunk.document_id == doc.id).all() if c.chroma_id]
    backup = collection.get(ids=old_ids, include=["embeddings", "documents", "metadatas"]) if old_ids else None

    new_ids = [f"{doc.id}-{i}" for i in range(len(new_chunks))]
    metadatas = [
        {"document_id": doc.id, "filename": doc.filename, "chunk_index": i, "source_type": "pdf",
         "page_start": c["page_start"], "page_end": c["page_end"]}
        for i, c in enumerate(new_chunks)
    ]
    try:
        db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
        db.add_all([
            Chunk(document_id=doc.id, content=c["text"], chroma_id=new_ids[i],
                  page_start=c["page_start"], page_end=c["page_end"])
            for i, c in enumerate(new_chunks)
        ])
        db.flush()
        if old_ids:
            collection.delete(ids=old_ids)
        collection.add(ids=new_ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
        db.commit()
    except Exception:
        db.rollback()
        try:
            collection.delete(ids=new_ids)
        except Exception:
            pass
        if backup and backup.get("ids"):
            collection.add(ids=backup["ids"], embeddings=backup["embeddings"],
                           documents=backup["documents"], metadatas=backup["metadatas"])
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Re-index old PDFs so they get page citations.")
    parser.add_argument("--apply", action="store_true", help="make the changes (default: dry run)")
    parser.add_argument("--force", action="store_true", help="also redo PDFs that already have page numbers")
    parser.add_argument("--ids", type=int, nargs="*", help="only these document ids")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    from app.database.db import SessionLocal
    from app.models.document import Document

    db = SessionLocal()
    try:
        query = db.query(Document).filter(Document.source_type == "pdf")
        if args.ids:
            query = query.filter(Document.id.in_(args.ids))
        docs = query.order_by(Document.id.asc()).all()

        plans = [(doc, *plan_document(db, doc, force=args.force)) for doc in docs]
        print(f"{'APPLY' if args.apply else 'DRY RUN'}: {len(docs)} PDF(s)\n")
        for _, report, _ in plans:
            if report["action"] == "reindex":
                print(f"  #{report['id']:<4} {report['name'][:40]:<40} re-index: {report['old_chunks']} -> "
                      f"{report['new_chunks']} chunks, {report['pages']} pages")
            else:
                print(f"  #{report['id']:<4} {report['name'][:40]:<40} skip: {report['reason']}")

        todo = [(doc, new) for doc, report, new in plans if new]
        if not args.apply:
            print(f"\n{len(todo)} would be re-indexed. Run again with --apply to do it.")
            return 0
        if not todo:
            print("\nNothing to do.")
            return 0

        from app.database.chroma import get_collection
        from app.services.embedding_service import get_embeddings
        collection = get_collection()
        done, failed = 0, 0
        for doc, new in todo:
            try:
                apply_document(db, collection, doc, new, get_embeddings)
                done += 1
                print(f"  re-indexed #{doc.id}")
            except Exception as e:
                failed += 1
                print(f"  FAILED #{doc.id}, left unchanged: {e}")
        print(f"\nDone: {done} re-indexed, {failed} failed.")
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
