"""
Multiple-choice quizzes for a document or a merged set (models in app/models/quiz.py).

Generating makes a new quiz (earlier quizzes and their attempts are kept);
the newest one is shown. An attempt is scored here from the submitted
answers, never from a score the browser sends.
"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.chunk import Chunk
from app.models.quiz import Quiz, QuizAttempt, QuizQuestion
from app.models.user import User
from app.routes.merged_sets import MIN_DOCUMENTS, _get_set, load_sources
from app.services.ai.flashcard_service import build_chunk_citations
from app.services.ai.merged_service import generate_merged_quiz
from app.services.ai.quiz_service import DEFAULT_QUESTIONS, generate_cited_quiz, generate_quiz
from app.services.ai.summary_service import AIGenerationError
from app.services.auth_service import get_current_user
from app.services.ownership import owned_document

router = APIRouter(tags=["Quizzes"])

MAX_QUESTIONS = 20
# Attempts listed with a quiz (newest first, across all of the document's or set's quizzes).
HISTORY_LIMIT = 20
EMPTY_QUIZ_MESSAGE = "The AI didn't return any usable questions. Please try again."


class AttemptRequest(BaseModel):
    # One per question, in order: the chosen option's index, or null if skipped.
    answers: List[Optional[int]]


def _question_dict(q: QuizQuestion) -> dict:
    return {
        "id": q.id,
        "question": q.question,
        "options": json.loads(q.options),
        "correct_index": q.correct_index,
        "explanation": q.explanation,
        "source_label": q.source_label,
        "source_url": q.source_url,
        "document_id": q.document_id,
    }


def _quiz_dict(quiz: Quiz) -> dict:
    return {
        "id": quiz.id,
        "created_at": quiz.created_at.isoformat() if quiz.created_at else None,
        "questions": [_question_dict(q) for q in quiz.questions],
        # Merged quizzes: a question whose document was deleted has lost its link.
        "stale": quiz.set_id is not None and any(q.document_id is None for q in quiz.questions),
    }


def _attempt_dict(a: QuizAttempt) -> dict:
    return {
        "id": a.id,
        "quiz_id": a.quiz_id,
        "score": a.score,
        "total": a.total,
        "answers": json.loads(a.answers),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _owner_filter(document_id: Optional[int], set_id: Optional[int]):
    return Quiz.document_id == document_id if document_id is not None else Quiz.set_id == set_id


def _quiz_state(db: Session, document_id: Optional[int] = None, set_id: Optional[int] = None) -> dict:
    """The newest quiz (or null) and recent attempts, for a document or a set."""
    owner = _owner_filter(document_id, set_id)
    quiz = db.query(Quiz).filter(owner).order_by(Quiz.id.desc()).first()
    attempts = (
        db.query(QuizAttempt).join(Quiz, Quiz.id == QuizAttempt.quiz_id).filter(owner)
        .order_by(QuizAttempt.id.desc()).limit(HISTORY_LIMIT).all()
    )
    return {
        "document_id": document_id,
        "set_id": set_id,
        "quiz": _quiz_dict(quiz) if quiz else None,
        "attempts": [_attempt_dict(a) for a in attempts],
    }


def _save_quiz(db: Session, questions: List[dict], document_id: Optional[int] = None, set_id: Optional[int] = None) -> None:
    quiz = Quiz(document_id=document_id, set_id=set_id)
    quiz.questions = [
        QuizQuestion(
            position=i,
            question=q["question"],
            options=json.dumps(q["options"]),
            correct_index=q["correct_index"],
            explanation=q.get("explanation") or "",
            source_label=q.get("source_label"),
            source_url=q.get("source_url"),
            document_id=q.get("document_id"),
        )
        for i, q in enumerate(questions)
    ]
    db.add(quiz)
    db.commit()


def score_answers(questions: List[QuizQuestion], answers: List[Optional[int]]) -> int:
    """How many answers are right; 400 if they don't fit the quiz."""
    if len(answers) != len(questions):
        raise HTTPException(
            status_code=400,
            detail=f"Expected {len(questions)} answers, one per question (null for a skipped question).",
        )
    score = 0
    for q, chosen in zip(questions, answers):
        if chosen is None:
            continue
        if not 0 <= chosen < len(json.loads(q.options)):
            raise HTTPException(status_code=400, detail="An answer isn't one of the question's options.")
        score += chosen == q.correct_index
    return score


def _record_attempt(db: Session, quiz: Optional[Quiz], body: AttemptRequest) -> dict:
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    score = score_answers(quiz.questions, body.answers)
    attempt = QuizAttempt(quiz_id=quiz.id, answers=json.dumps(body.answers), score=score, total=len(quiz.questions))
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return _attempt_dict(attempt)


# ─── Document quizzes ───


@router.get("/api/v1/documents/{document_id}/quiz")
def get_document_quiz(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    owned_document(db, document_id, user)
    return _quiz_state(db, document_id=document_id)


@router.post("/api/v1/documents/{document_id}/quiz")
def create_document_quiz(
    document_id: int,
    count: int = Query(DEFAULT_QUESTIONS, ge=1, le=MAX_QUESTIONS, description="Number of questions"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate a new quiz for the document (earlier quizzes and attempts are kept)."""
    doc = owned_document(db, document_id, user)
    if not doc.content or not doc.content.strip():
        raise HTTPException(status_code=400, detail="Document has no content to make a quiz from")

    rows = [
        c for c in db.query(Chunk).filter(Chunk.document_id == doc.id).order_by(Chunk.id.asc()).all()
        if c.content and c.content.strip()
    ]
    try:
        if rows:
            citations = build_chunk_citations(
                doc.source_type, doc.source_url, doc.filename,
                [(c.content, c.start_seconds) for c in rows],
                pages=[(c.page_start, c.page_end) for c in rows],
            )
            questions = generate_cited_quiz([c.content for c in rows], citations, count=count)
        else:
            questions = generate_quiz(doc.content, count=count)
    except AIGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not questions:
        raise HTTPException(status_code=502, detail=EMPTY_QUIZ_MESSAGE)

    _save_quiz(db, questions, document_id=doc.id)
    return _quiz_state(db, document_id=doc.id)


@router.post("/api/v1/documents/{document_id}/quiz/{quiz_id}/attempts")
def submit_document_attempt(
    document_id: int, quiz_id: int, body: AttemptRequest,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    owned_document(db, document_id, user)
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id, Quiz.document_id == document_id).first()
    attempt = _record_attempt(db, quiz, body)
    return {"attempt": attempt, **_quiz_state(db, document_id=document_id)}


# ─── Merged-set quizzes ───


@router.get("/api/v1/merged-sets/{set_id}/quiz")
def get_merged_quiz(set_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_set(db, set_id, user)
    return _quiz_state(db, set_id=set_id)


@router.post("/api/v1/merged-sets/{set_id}/quiz")
def create_merged_quiz(
    set_id: int,
    count: int = Query(DEFAULT_QUESTIONS, ge=1, le=MAX_QUESTIONS, description="Number of questions"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate a new quiz covering every document in the set."""
    merged = _get_set(db, set_id, user)
    sources = load_sources(db, merged)
    if len(sources) < MIN_DOCUMENTS:
        raise HTTPException(
            status_code=400,
            detail="This set has fewer than 2 documents left, so there's nothing to merge. "
                   "Create a new set from the Library instead.",
        )
    if not any(s.chunks for s in sources):
        raise HTTPException(status_code=400, detail="These documents have no text to make a quiz from.")

    try:
        questions = generate_merged_quiz(sources, count=count)
    except AIGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not questions:
        raise HTTPException(status_code=502, detail=EMPTY_QUIZ_MESSAGE)

    _save_quiz(db, questions, set_id=set_id)
    return _quiz_state(db, set_id=set_id)


@router.post("/api/v1/merged-sets/{set_id}/quiz/{quiz_id}/attempts")
def submit_merged_attempt(
    set_id: int, quiz_id: int, body: AttemptRequest,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_set(db, set_id, user)
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id, Quiz.set_id == set_id).first()
    attempt = _record_attempt(db, quiz, body)
    return {"attempt": attempt, **_quiz_state(db, set_id=set_id)}
