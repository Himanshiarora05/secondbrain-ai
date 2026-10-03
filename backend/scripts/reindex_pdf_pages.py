"""
Re-index PDFs uploaded before page tracking, so they get page citations.

WHY THIS SCRIPT EXISTS
-----------------------
PDFs uploaded before page tracking have chunks without page_start/page_end,
so their summaries, flashcards and search results can't cite "p. 12". The
original files are still in uploads/, so this re-reads each one page by page
and rebuilds its chunks and their search vectors with page ranges.

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
Per document: the new chunks are embedded first (nothing changed yet), then
the old chunks and vectors are replaced in one database transaction, so a
failure leaves the document exactly as it was.

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


def apply_document(db, doc, new_chunks, embed):
    """Swap `doc`'s chunks and their vectors for `new_chunks` in one transaction."""
    from app.models.chunk import Chunk, ChunkEmbedding

    texts = [c["text"] for c in new_chunks]
    embeddings = embed(texts)  # may raise: nothing has changed yet
    try:
        # The old chunks' vectors go with them (ON DELETE CASCADE).
        db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
        db.add_all([
            Chunk(document_id=doc.id, content=c["text"], page_start=c["page_start"], page_end=c["page_end"],
                  embedding=ChunkEmbedding(embedding=embeddings[i]))
            for i, c in enumerate(new_chunks)
        ])
        db.commit()
    except Exception:
        db.rollback()
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

        from app.services.embedding_service import get_embeddings
        done, failed = 0, 0
        for doc, new in todo:
            try:
                apply_document(db, doc, new, get_embeddings)
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
