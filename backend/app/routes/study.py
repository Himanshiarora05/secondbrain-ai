from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database.db import get_db
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.summary import Summary
from app.models.flashcard import Flashcard
from app.models.user import User
from app.routes.review import schedule_dict
from app.services.auth_service import get_current_user
from app.services.ownership import owned_document
from app.services.ai.summary_service import (
    generate_summary,
    generate_cited_summary,
    generate_youtube_summary,
    append_source_link,
    AIGenerationError,
)
from app.services.ai.flashcard_service import (
    generate_flashcards,
    generate_cited_flashcards,
    build_chunk_citations,
)

router = APIRouter(prefix="/api/v1/documents", tags=["Study"])


def _lock_document(db: Session, document_id: int) -> None:
    """Row-lock the document until commit/rollback so saves for it run one at a time.

    Only taken right before writing, never around the (slow) LLM call.
    """
    db.query(Document.id).filter(Document.id == document_id).with_for_update().first()


@router.post("/{document_id}/summary")
def create_or_regenerate_summary(
    document_id: int,
    regenerate: bool = Query(False, description="Force regeneration of summary even if one exists"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = owned_document(db, document_id, user)

    existing_summary = db.query(Summary).filter(Summary.document_id == document_id).first()

    if existing_summary and not regenerate:
        return {
            "document_id": doc.id,
            "summary": existing_summary.content,
        }

    if not doc.content or not doc.content.strip():
        raise HTTPException(status_code=400, detail="Document has no content to summarize")

    timed_chunks = []
    if doc.source_type == "youtube" and doc.source_url:
        timed_chunks = [
            (c.start_seconds, c.content)
            for c in db.query(Chunk)
            .filter(Chunk.document_id == doc.id, Chunk.start_seconds.isnot(None))
            .order_by(Chunk.start_seconds.asc(), Chunk.id.asc())
            .all()
            if c.content and c.content.strip()
        ]

    # PDFs and images (page ranges) and PowerPoint decks (slide markers) cite
    # "(p. 12)" / "(Slide 4)" from their stored chunks, like YouTube timestamps.
    cited_chunks, citations = [], []
    if doc.source_type in ("pdf", "image", "pptx"):
        rows = [
            c for c in db.query(Chunk)
            .filter(Chunk.document_id == doc.id)
            .order_by(Chunk.id.asc())
            .all()
            if c.content and c.content.strip()
        ]
        citations = build_chunk_citations(
            doc.source_type, doc.source_url, doc.filename,
            [(c.content, c.start_seconds) for c in rows],
            pages=[(c.page_start, c.page_end) for c in rows],
        )
        # A PDF uploaded before page tracking has no citations: plain summary as before.
        if any(citations):
            cited_chunks = [c.content for c in rows]

    try:
        if timed_chunks:
            summary_text = generate_youtube_summary(timed_chunks, doc.source_url)
        elif cited_chunks:
            summary_text = generate_cited_summary(cited_chunks, citations)
        else:
            summary_text = generate_summary(doc.content)
            if doc.source_type == "website" and doc.source_url:
                summary_text = append_source_link(summary_text, doc.filename, doc.source_url)
    except AIGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Another request may have saved a summary while this one was generating
    # (double click, two tabs, React StrictMode running the page effect twice).
    _lock_document(db, doc.id)
    existing_summary = db.query(Summary).filter(Summary.document_id == document_id).first()
    if existing_summary and not regenerate:
        db.commit()  # releases the lock; keep the summary that was saved first
        return {
            "document_id": doc.id,
            "summary": existing_summary.content,
        }

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
    user: User = Depends(get_current_user),
):
    doc = owned_document(db, document_id, user)

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
    user: User = Depends(get_current_user),
):
    doc = owned_document(db, document_id, user)

    if not doc.content or not doc.content.strip():
        raise HTTPException(status_code=400, detail="Document has no content to generate flashcards")

    chunk_rows = [
        c for c in db.query(Chunk)
        .filter(Chunk.document_id == doc.id)
        .order_by(Chunk.id.asc())
        .all()
        if c.content and c.content.strip()
    ]

    try:
        if chunk_rows:
            citations = build_chunk_citations(
                doc.source_type,
                doc.source_url,
                doc.filename,
                [(c.content, c.start_seconds) for c in chunk_rows],
                pages=[(c.page_start, c.page_end) for c in chunk_rows],
            )
            cards_data = generate_cited_flashcards([c.content for c in chunk_rows], citations, count=count)
        else:
            cards_data = generate_flashcards(doc.content, count=count)
    except AIGenerationError as e:
        raise HTTPException(
            status_code=502,
            detail=f"{e} Your existing flashcards were not changed.",
        )

    if not cards_data:
        raise HTTPException(
            status_code=502,
            detail="The AI didn't return any flashcards. Please try again. Your existing flashcards were not changed.",
        )

    # Replace existing flashcards for this document only after non-empty return.
    # The lock makes concurrent replaces run one after the other; without it both
    # deletes can run before either insert commits and the deck ends up doubled.
    _lock_document(db, doc.id)
    db.query(Flashcard).filter(Flashcard.document_id == document_id).delete()

    new_cards = [
        Flashcard(
            document_id=doc.id,
            question=c["question"],
            answer=c["answer"],
            source_label=c.get("source_label"),
            source_url=c.get("source_url"),
        )
        for c in cards_data
    ]
    db.add_all(new_cards)
    db.commit()

    # Re-query saved cards to return database ids
    saved_cards = db.query(Flashcard).filter(Flashcard.document_id == document_id).order_by(Flashcard.id.asc()).all()

    return {
        "document_id": doc.id,
        "flashcards": [_flashcard_dict(card) for card in saved_cards],
    }


@router.get("/{document_id}/flashcards")
def get_document_flashcards(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = owned_document(db, document_id, user)

    cards = db.query(Flashcard).filter(Flashcard.document_id == document_id).order_by(Flashcard.id.asc()).all()

    return {
        "document_id": doc.id,
        "flashcards": [_flashcard_dict(card) for card in cards],
    }


def _flashcard_dict(card: Flashcard) -> dict:
    return {
        "id": card.id,
        "question": card.question,
        "answer": card.answer,
        "source_label": card.source_label,
        "source_url": card.source_url,
        **schedule_dict(card),
    }
