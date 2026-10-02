from datetime import datetime
from sqlalchemy import Column, Date, Float, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database.db import Base
from app.services.spaced_repetition import DEFAULT_EASE


class ReviewScheduleMixin:
    """SM-2 review state, shared by document cards and merged-set cards.

    A card nobody has rated yet has due_date null and counts as due (a new
    card); its first rating puts it on the schedule (app/services/spaced_repetition.py).
    Regenerating a deck replaces its cards, so their schedule starts over.
    """
    ease = Column(Float, default=DEFAULT_EASE, nullable=False)
    interval_days = Column(Integer, default=0, nullable=False)
    repetitions = Column(Integer, default=0, nullable=False)
    due_date = Column(Date, nullable=True, index=True)
    last_reviewed_at = Column(DateTime, nullable=True)
    # The (local) day the card was first rated; new cards started today count
    # against the daily new-card limit (app/routes/review.py).
    first_reviewed_on = Column(Date, nullable=True, index=True)


class Flashcard(ReviewScheduleMixin, Base):
    __tablename__ = "flashcards"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    # Where the card came from, built by code at generation time (never by the
    # model): "02:05" + video link, page title + page link, or "Slide 4" (no link).
    # Both null for PDF/Word cards and for cards generated before citations existed.
    source_label = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="flashcards")
