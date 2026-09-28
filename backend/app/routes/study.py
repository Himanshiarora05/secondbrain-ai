from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database.db import get_db
from app.models.document import Document
from app.models.summary import Summary
from app.models.flashcard import Flashcard
from app.services.ai.summary_service import generate_summary, AIGenerationError
from app.services.ai.flashcard_service import generate_flashcards

router = APIRouter(prefix="/api/v1/documents", tags=["Study"])


@router.post("/{document_id}/summary")
def create_or_regenerate_summary(
    document_id: int,
    regenerate: bool = Query(False, description="Force regeneration of summary even if one exists"),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    existing_summary = db.query(Summary).filter(Summary.document_id == document_id).first()

    if existing_summary and not regenerate:
        return {
            "document_id": doc.id,
            "summary": existing_summary.content,
        }

    if not doc.content or not doc.content.strip():
        raise HTTPException(status_code=400, detail="Document has no content to summarize")

    try:
        summary_text = generate_summary(doc.content)
    except AIGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if existing_summary:
        existing_summary.content = summary_text
        db.commit()
        db.refresh(existing_summary)
        saved_content = existing_summary.content
    else:
        new_summary = Summary(document_id=doc.id, content=summary_text)
        db.add(new_summary)
        db.commit()
        db.refresh(new_summary)
        saved_content = new_summary.content

    return {
        "document_id": doc.id,
        "summary": saved_content,
    }


@router.get("/{document_id}/summary")
def get_document_summary(
    document_id: int,
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    summary = db.query(Summary).filter(Summary.document_id == document_id).first()
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found for this document")

    return {
        "document_id": doc.id,
        "summary": summary.content,
    }


@router.post("/{document_id}/flashcards")
def create_flashcards(
    document_id: int,
    count: int = Query(10, ge=1, le=50, description="Number of flashcards to generate"),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.content or not doc.content.strip():
        raise HTTPException(status_code=400, detail="Document has no content to generate flashcards")

    try:
        cards_data = generate_flashcards(doc.content, count=count)
    except AIGenerationError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Flashcard generation failed, your existing flashcards were not changed: {str(e)}",
        )

    if not cards_data:
        raise HTTPException(
            status_code=502,
            detail="Flashcard generation failed, your existing flashcards were not changed: no cards generated",
        )

    # Replace existing flashcards for this document only after non-empty return
    db.query(Flashcard).filter(Flashcard.document_id == document_id).delete()

    new_cards = [
        Flashcard(document_id=doc.id, question=c["question"], answer=c["answer"])
        for c in cards_data
    ]
    db.add_all(new_cards)
    db.commit()

    # Re-query saved cards to return database ids
    saved_cards = db.query(Flashcard).filter(Flashcard.document_id == document_id).order_by(Flashcard.id.asc()).all()

    return {
        "document_id": doc.id,
        "flashcards": [
            {
                "id": card.id,
                "question": card.question,
                "answer": card.answer,
            }
            for card in saved_cards
        ],
    }


@router.get("/{document_id}/flashcards")
def get_document_flashcards(
    document_id: int,
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    cards = db.query(Flashcard).filter(Flashcard.document_id == document_id).order_by(Flashcard.id.asc()).all()

    return {
        "document_id": doc.id,
        "flashcards": [
            {
                "id": card.id,
                "question": card.question,
                "answer": card.answer,
            }
            for card in cards
        ],
    }
