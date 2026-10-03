import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.ownership import owned_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Documents"])

UPLOAD_DIR = Path("uploads")

MAX_NAME_LENGTH = 255


@router.get("/documents")
def list_documents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # The user's documents with their chunk counts and text length (the merge
    # pickers mark documents over the per-document limit of a merged set)
    results = (
        db.query(
            Document.id,
            Document.file_id,
            Document.filename,
            Document.source_type,
            Document.source_url,
            func.count(Chunk.id).label("total_chunks"),
            func.coalesce(func.length(Document.content), 0).label("char_count"),
        )
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .filter(Document.user_id == user.id)
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
            "char_count": row.char_count,
        }
        for row in results
    ]


class RenameRequest(BaseModel):
    filename: str


@router.patch("/documents/{document_id}")
def rename_document(
    document_id: int, body: RenameRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Change a document's display name. Search results read the name from the
    document row, so nothing else needs updating."""
    name = " ".join(body.filename.split())
    if not name:
        raise HTTPException(status_code=400, detail="The name can't be empty.")
    if len(name) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"The name can be at most {MAX_NAME_LENGTH} characters.")

    doc = owned_document(db, document_id, user)
    if name == doc.filename:
        return {"id": doc.id, "filename": doc.filename}

    try:
        doc.filename = name
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to rename document {document_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Couldn't rename the document. Please try again.")

    return {"id": doc.id, "filename": doc.filename}


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = owned_document(db, document_id, user)

    file_id = doc.file_id
    filename = doc.filename

    # 1. Delete the Document (cascade removes its chunks, their search vectors, summary, flashcards)
    db.delete(doc)
    db.commit()

    # 2. Remove physical file from uploads/ if it exists
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

