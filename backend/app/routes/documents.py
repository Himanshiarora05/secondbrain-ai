import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database.db import SessionLocal, get_db
from app.database.chroma import get_collection
from app.models.document import Document
from app.models.chunk import Chunk

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Documents"])

UPLOAD_DIR = Path("uploads")

MAX_NAME_LENGTH = 255


@router.get("/documents")
def list_documents():
    db = SessionLocal()

    try:
        # Query documents with their chunk counts
        results = (
            db.query(
                Document.id,
                Document.file_id,
                Document.filename,
                Document.source_type,
                Document.source_url,
                func.count(Chunk.id).label("total_chunks"),
            )
            .outerjoin(Chunk, Chunk.document_id == Document.id)
            .group_by(Document.id)
            .order_by(Document.id)
            .all()
        )

        return [
            {
                "id": row.id,
                "file_id": row.file_id,
                "filename": row.filename,
                "source_type": row.source_type or "pdf",
                "source_url": row.source_url,
                "total_chunks": row.total_chunks,
            }
            for row in results
        ]

    finally:
        db.close()


class RenameRequest(BaseModel):
    filename: str


@router.patch("/documents/{document_id}")
def rename_document(document_id: int, body: RenameRequest, db: Session = Depends(get_db)):
    """Change a document's display name. Search results show the name stored in
    Chroma metadata, so the document's vectors are updated too: Chroma first,
    then the database, and Chroma is put back if the database write fails."""
    name = " ".join(body.filename.split())
    if not name:
        raise HTTPException(status_code=400, detail="The name can't be empty.")
    if len(name) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"The name can be at most {MAX_NAME_LENGTH} characters.")

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if name == doc.filename:
        return {"id": doc.id, "filename": doc.filename}

    collection = get_collection()
    stored = collection.get(where={"document_id": document_id}, include=["metadatas"])
    ids, old_metadatas = stored["ids"], stored["metadatas"]
    try:
        if ids:
            collection.update(ids=ids, metadatas=[{**m, "filename": name} for m in old_metadatas])
        doc.filename = name
        db.commit()
    except Exception as e:
        db.rollback()
        if ids:
            try:
                collection.update(ids=ids, metadatas=old_metadatas)
            except Exception:
                logger.error(f"Could not restore search names for document {document_id}", exc_info=True)
        logger.error(f"Failed to rename document {document_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Couldn't rename the document. Please try again.")

    return {"id": doc.id, "filename": doc.filename}


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_id = doc.file_id
    filename = doc.filename

    # 1. Collect all chunk IDs and chroma IDs before deleting chunk rows
    chunks = db.query(Chunk).filter(Chunk.document_id == document_id).all()
    chroma_ids = [c.chroma_id for c in chunks if c.chroma_id]

    # 2. Delete vectors from Chroma collection
    collection = get_collection()
    if chroma_ids:
        try:
            collection.delete(ids=chroma_ids)
        except Exception as e:
            logger.warning(f"Error deleting Chroma IDs {chroma_ids} for document {document_id}: {e}")

    # Fallback/safety delete by metadata where document_id == document_id
    try:
        collection.delete(where={"document_id": document_id})
    except Exception as e:
        logger.warning(f"Error deleting Chroma vectors with document_id={document_id}: {e}")

    # 3. Delete Document from PostgreSQL (cascade delete removes chunks, summary, flashcards)
    db.delete(doc)
    db.commit()

    # 4. Remove physical file from uploads/ if it exists
    if file_id:
        for f in UPLOAD_DIR.glob(f"{file_id}.*"):
            try:
                f.unlink()
                logger.info(f"Deleted uploaded file: {f}")
            except Exception as e:
                logger.warning(f"Could not delete physical file {f}: {e}")

    return {
        "message": f"Document '{filename}' and associated chunks, summaries, and flashcards deleted successfully",
        "id": document_id,
    }

