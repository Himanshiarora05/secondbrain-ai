"""
Spaced repetition: rate a card (Again / Good / Easy) and list the cards due
today across every document deck and merged-set deck the user owns.

The schedule itself is SM-2 (app/services/spaced_repetition.py). "Today" is
the browser's local date when it sends one (see local_today), so a card due
"tomorrow" doesn't turn up early or late for users far from UTC.
"""

from datetime import date, datetime
from typing import Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.document import Document
from app.models.flashcard import Flashcard
from app.models.merged_set import MergedFlashcard, MergedSet
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.spaced_repetition import local_today, review

router = APIRouter(prefix="/api/v1/review", tags=["Review"])

CardKind = Literal["document", "merged"]


class ReviewRequest(BaseModel):
    grade: Literal["again", "good", "easy"]
    # The browser's local date (YYYY-MM-DD); the server's UTC date if missing or implausible.
    today: Optional[date] = None


def schedule_dict(card: Union[Flashcard, MergedFlashcard]) -> dict:
    """A card's review state, included in every card the API returns."""
    return {
        "ease": card.ease,
        "interval_days": card.interval_days,
        "repetitions": card.repetitions,
        # Null until the card is first rated; such a new card counts as due.
        "due_date": card.due_date.isoformat() if card.due_date else None,
        "last_reviewed_at": card.last_reviewed_at.isoformat() if card.last_reviewed_at else None,
    }


def _today(client_today: Optional[date]) -> date:
    return local_today(client_today, datetime.utcnow().date())


def _owned_card(db: Session, kind: str, card_id: int, user: User) -> Union[Flashcard, MergedFlashcard]:
    """The user's card, row-locked until commit, or 404 (another user's card looks missing)."""
    if kind == "document":
        query = db.query(Flashcard).join(Document, Document.id == Flashcard.document_id).filter(
            Flashcard.id == card_id, Document.user_id == user.id,
        ).with_for_update(of=Flashcard)
    else:
        query = db.query(MergedFlashcard).join(MergedSet, MergedSet.id == MergedFlashcard.set_id).filter(
            MergedFlashcard.id == card_id, MergedSet.user_id == user.id,
        ).with_for_update(of=MergedFlashcard)
    card = query.first()
    if not card:
        raise HTTPException(status_code=404, detail="Flashcard not found")
    return card


@router.post("/cards/{kind}/{card_id}")
def review_card(
    kind: CardKind,
    card_id: int,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    card = _owned_card(db, kind, card_id, user)
    schedule = review(card.ease, card.interval_days, card.repetitions, body.grade, _today(body.today))
    card.ease = schedule.ease
    card.interval_days = schedule.interval_days
    card.repetitions = schedule.repetitions
    card.due_date = schedule.due_date
    card.last_reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(card)
    return {"kind": kind, "id": card.id, **schedule_dict(card)}


def _due_document_cards(db: Session, user: User, today: date):
    return (
        db.query(Flashcard, Document.id, Document.filename, Document.source_type)
        .join(Document, Document.id == Flashcard.document_id)
        .filter(Document.user_id == user.id, or_(Flashcard.due_date.is_(None), Flashcard.due_date <= today))
    )


def _due_merged_cards(db: Session, user: User, today: date):
    return (
        db.query(MergedFlashcard, MergedSet.id, MergedSet.name)
        .join(MergedSet, MergedSet.id == MergedFlashcard.set_id)
        .filter(MergedSet.user_id == user.id, or_(MergedFlashcard.due_date.is_(None), MergedFlashcard.due_date <= today))
    )


@router.get("/due")
def due_cards(
    today: Optional[date] = Query(None, description="The browser's local date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Every card due on or before today, oldest due date first, then never-rated cards, with their deck."""
    day = _today(today)
    cards = []
    for card, doc_id, filename, source_type in _due_document_cards(db, user, day).all():
        cards.append({
            "kind": "document", "id": card.id, "question": card.question, "answer": card.answer,
            "source_label": card.source_label, "source_url": card.source_url,
            "deck_id": doc_id, "deck_name": filename, "deck_source_type": source_type or "pdf",
            **schedule_dict(card),
        })
    for card, set_id, name in _due_merged_cards(db, user, day).all():
        cards.append({
            "kind": "merged", "id": card.id, "question": card.question, "answer": card.answer,
            "source_label": card.source_label, "source_url": card.source_url,
            "deck_id": set_id, "deck_name": name, "deck_source_type": "merged",
            **schedule_dict(card),
        })
    # Reviews already on the schedule come before new cards.
    cards.sort(key=lambda c: (c["due_date"] is None, c["due_date"] or "", c["kind"], c["deck_id"], c["id"]))
    return {"today": day.isoformat(), "count": len(cards), "cards": cards}


@router.get("/due/count")
def due_count(
    today: Optional[date] = Query(None, description="The browser's local date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Just the number, for the sidebar."""
    day = _today(today)
    count = _due_document_cards(db, user, day).count() + _due_merged_cards(db, user, day).count()
    return {"today": day.isoformat(), "count": count}
