"""
Spaced repetition: rate a card (Again / Good / Easy) and list the cards due
today across every document deck and merged-set deck the user owns.

The schedule itself is SM-2 (app/services/spaced_repetition.py). "Today" is
the browser's local date when it sends one (see local_today), so a card due
"tomorrow" doesn't turn up early or late for users far from UTC.

Due today = every scheduled card due on or before today, plus new (never
rated) cards up to the daily limit (NEW_CARDS_PER_DAY, default 20) minus the
new cards already started today, anywhere: rating a new card in a deck uses
up the day's allowance too (first_reviewed_on). Oldest new cards come first.
"""

import os
from datetime import date, datetime
from typing import Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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
DEFAULT_NEW_CARDS_PER_DAY = 20


def new_cards_per_day() -> int:
    """NEW_CARDS_PER_DAY from .env (0 turns new cards off), else 20."""
    try:
        value = int(os.getenv("NEW_CARDS_PER_DAY", "").strip())
    except ValueError:
        return DEFAULT_NEW_CARDS_PER_DAY
    return value if value >= 0 else DEFAULT_NEW_CARDS_PER_DAY


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
        # Null until the card is first rated; such a new card counts as due (within the daily limit).
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
    today = _today(body.today)
    schedule = review(card.ease, card.interval_days, card.repetitions, body.grade, today)
    if card.due_date is None and card.first_reviewed_on is None:
        card.first_reviewed_on = today  # a new card started today: counts against the daily limit
    card.ease = schedule.ease
    card.interval_days = schedule.interval_days
    card.repetitions = schedule.repetitions
    card.due_date = schedule.due_date
    card.last_reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(card)
    return {"kind": kind, "id": card.id, **schedule_dict(card)}


def _document_cards(db: Session, user: User):
    return (
        db.query(Flashcard, Document.id, Document.filename, Document.source_type)
        .join(Document, Document.id == Flashcard.document_id)
        .filter(Document.user_id == user.id)
    )


def _merged_cards(db: Session, user: User):
    return (
        db.query(MergedFlashcard, MergedSet.id, MergedSet.name)
        .join(MergedSet, MergedSet.id == MergedFlashcard.set_id)
        .filter(MergedSet.user_id == user.id)
    )


def _new_left_today(db: Session, user: User, today: date, limit: int) -> int:
    started = (
        _document_cards(db, user).filter(Flashcard.first_reviewed_on == today).count()
        + _merged_cards(db, user).filter(MergedFlashcard.first_reviewed_on == today).count()
    )
    return max(0, limit - started)


def _card_dict(kind: str, card, deck_id: int, deck_name: str, deck_source_type: str) -> dict:
    return {
        "kind": kind, "id": card.id, "question": card.question, "answer": card.answer,
        "source_label": card.source_label, "source_url": card.source_url,
        "deck_id": deck_id, "deck_name": deck_name, "deck_source_type": deck_source_type,
        **schedule_dict(card),
    }


def _due_and_new(db: Session, user: User, today: date):
    """(scheduled cards due by today, every new card oldest first), as API dicts."""
    scheduled, new = [], []
    for card, doc_id, filename, source_type in _document_cards(db, user).filter(
        (Flashcard.due_date.is_(None)) | (Flashcard.due_date <= today)
    ).all():
        item = (card.created_at, _card_dict("document", card, doc_id, filename, source_type or "pdf"))
        (new if card.due_date is None else scheduled).append(item)
    for card, set_id, name in _merged_cards(db, user).filter(
        (MergedFlashcard.due_date.is_(None)) | (MergedFlashcard.due_date <= today)
    ).all():
        item = (card.created_at, _card_dict("merged", card, set_id, name, "merged"))
        (new if card.due_date is None else scheduled).append(item)
    scheduled_cards = sorted((c for _, c in scheduled), key=lambda c: (c["due_date"], c["kind"], c["deck_id"], c["id"]))
    new_cards = [c for _, c in sorted(new, key=lambda t: (t[0] or datetime.min, t[1]["kind"], t[1]["id"]))]
    return scheduled_cards, new_cards


def _counts(review_count: int, new_shown: int, new_total: int, new_left: int, limit: int, today: date) -> dict:
    return {
        "today": today.isoformat(),
        "count": review_count + new_shown,
        "review_count": review_count,
        "new_count": new_shown,
        # New cards waiting beyond today's limit.
        "new_waiting": new_total - new_shown,
        "new_limit": limit,
        "new_left_today": new_left,
    }


@router.get("/due")
def due_cards(
    today: Optional[date] = Query(None, description="The browser's local date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Every scheduled card due by today (oldest due first), then today's share of new cards."""
    day = _today(today)
    limit = new_cards_per_day()
    scheduled, new = _due_and_new(db, user, day)
    new_left = _new_left_today(db, user, day, limit)
    shown = new[:new_left]
    return {**_counts(len(scheduled), len(shown), len(new), new_left, limit, day), "cards": scheduled + shown}


@router.get("/due/count")
def due_count(
    today: Optional[date] = Query(None, description="The browser's local date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Just the numbers, for the sidebar."""
    day = _today(today)
    limit = new_cards_per_day()
    scheduled = _document_cards(db, user).filter(Flashcard.due_date <= day).count() \
        + _merged_cards(db, user).filter(MergedFlashcard.due_date <= day).count()
    new_total = _document_cards(db, user).filter(Flashcard.due_date.is_(None)).count() \
        + _merged_cards(db, user).filter(MergedFlashcard.due_date.is_(None)).count()
    new_left = _new_left_today(db, user, day, limit)
    return _counts(scheduled, min(new_total, new_left), new_total, new_left, limit, day)
