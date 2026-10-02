"""
Merged sets: several documents studied together, with one summary and one
flashcard deck built from all of them.

Kept entirely apart from the per-document `summaries` / `flashcards` tables,
so nothing done to a set can change a document's own summary or deck.
Deleting a set removes only its own rows. Deleting a document removes its
membership (ON DELETE CASCADE) and unlinks its merged cards (ON DELETE SET
NULL); both happen in Postgres, since Document has no relationship to these
tables. The set's saved summary and cards stay readable because their
citation text was stored when they were generated.
"""

from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.db import Base
from app.models.flashcard import ReviewScheduleMixin


class MergedSet(Base):
    __tablename__ = "merged_sets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    # Owner (null for sets from before accounts, until assign_documents_to_user.py runs).
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    members = relationship(
        "MergedSetDocument", back_populates="merged_set", cascade="all, delete-orphan",
        order_by="MergedSetDocument.position", passive_deletes=True,
    )
    summary = relationship(
        "MergedSummary", back_populates="merged_set", uselist=False, cascade="all, delete-orphan", passive_deletes=True,
    )
    flashcards = relationship(
        "MergedFlashcard", back_populates="merged_set", cascade="all, delete-orphan", passive_deletes=True,
    )


class MergedSetDocument(Base):
    __tablename__ = "merged_set_documents"
    __table_args__ = (UniqueConstraint("set_id", "document_id", name="uq_merged_set_document"),)

    id = Column(Integer, primary_key=True)
    set_id = Column(Integer, ForeignKey("merged_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    # Order the documents were selected in; also each source's number in citations (position + 1).
    position = Column(Integer, nullable=False)

    merged_set = relationship("MergedSet", back_populates="members")


class MergedSummary(Base):
    __tablename__ = "merged_summaries"

    id = Column(Integer, primary_key=True)
    set_id = Column(Integer, ForeignKey("merged_sets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    content = Column(Text, nullable=False)
    # JSON list of the document ids it was generated from; a member that has
    # since been deleted makes the summary stale.
    document_ids = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merged_set = relationship("MergedSet", back_populates="summary")


class MergedFlashcard(ReviewScheduleMixin, Base):
    __tablename__ = "merged_flashcards"

    id = Column(Integer, primary_key=True)
    set_id = Column(Integer, ForeignKey("merged_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    # The source the card came from; null once that document is deleted.
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    # Built by code at generation time, e.g. "Graph_PPT.pdf · p. 12" (+ link for YouTube/websites).
    source_label = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merged_set = relationship("MergedSet", back_populates="flashcards")
