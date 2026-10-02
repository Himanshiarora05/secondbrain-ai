"""
Multiple-choice quizzes for a document or a merged set, and the attempts at them.

A quiz belongs to exactly one document or one merged set (CHECK constraint)
and is deleted with it (ON DELETE CASCADE, in Postgres, like merged sets:
Document has no relationship to these tables). Generating a new quiz never
replaces an old one, so every saved attempt keeps the questions it answered;
the newest quiz is the one shown. A merged quiz's question loses its
document_id (ON DELETE SET NULL) when that document is deleted, which makes
the quiz stale, like merged flashcards.
"""

from datetime import datetime
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.database.db import Base


class Quiz(Base):
    __tablename__ = "quizzes"
    __table_args__ = (
        CheckConstraint("(document_id IS NULL) <> (set_id IS NULL)", name="ck_quiz_one_owner"),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    set_id = Column(Integer, ForeignKey("merged_sets.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    questions = relationship(
        "QuizQuestion", back_populates="quiz", cascade="all, delete-orphan",
        order_by="QuizQuestion.position", passive_deletes=True,
    )
    attempts = relationship(
        "QuizAttempt", back_populates="quiz", cascade="all, delete-orphan", passive_deletes=True,
    )


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    question = Column(Text, nullable=False)
    # JSON list of the 4 option texts, in the order shown.
    options = Column(Text, nullable=False)
    correct_index = Column(Integer, nullable=False)
    explanation = Column(Text, nullable=False, default="")
    # Built by code at generation time, like flashcards: "p. 12", "Slide 4",
    # "02:05" + link; merged quizzes name the source ("Graph_PPT.pdf · p. 12").
    source_label = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    # Merged quizzes only: the source the question came from; null once it's deleted.
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)

    quiz = relationship("Quiz", back_populates="questions")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id = Column(Integer, primary_key=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    # JSON list, one per question in order: the chosen option's index, or null if skipped.
    answers = Column(Text, nullable=False)
    score = Column(Integer, nullable=False)
    total = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    quiz = relationship("Quiz", back_populates="attempts")
