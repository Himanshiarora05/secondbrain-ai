"""
Ownership checks shared by the routes.

Another user's document or set is reported exactly like one that doesn't
exist (404, same message), so IDs can't be probed to learn what exists.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User


def owned_document(db: Session, document_id: int, user: User) -> Document:
    """The user's document with this id, or 404."""
    doc = db.query(Document).filter(Document.id == document_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
