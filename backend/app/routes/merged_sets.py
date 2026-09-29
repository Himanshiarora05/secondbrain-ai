"""
Merged sets: 2-8 documents studied together (see app/models/merged_set.py).

A set is created from a selection in the Library. Creating one with exactly
the documents of an existing set returns that set instead of a copy.
"""

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.merged_set import MergedFlashcard, MergedSet, MergedSetDocument, MergedSummary
from app.models.user import User
from app.routes.documents import MAX_NAME_LENGTH
from app.services.ai.flashcard_service import build_chunk_citations
from app.services.ai.merged_service import MergedSource, generate_merged_flashcards, generate_merged_summary
from app.services.ai.summary_service import AIGenerationError
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/v1/merged-sets", tags=["Merged sets"])

MIN_DOCUMENTS = 2
MAX_DOCUMENTS = 8
# Total extracted text across the set. One merged summary of long documents
# takes many AI calls (~1 per 3,000 characters), and any failure fails it all.
MAX_TOTAL_CHARS = 80_000

# Any fixed number: serialises set creation so a double click can't create two copies.
_CREATE_LOCK_KEY = 7_340_001


class CreateMergedSetRequest(BaseModel):
    document_ids: List[int]
    name: Optional[str] = None


class RenameMergedSetRequest(BaseModel):
    name: str


def _clean_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not name:
        raise HTTPException(status_code=400, detail="The name can't be empty.")
    if len(name) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"The name can be at most {MAX_NAME_LENGTH} characters.")
    return name


def default_set_name(filenames: List[str]) -> str:
    """"A + B" for two documents, "A + B + 3 more" for more."""
    name = " + ".join(filenames[:2])
    if len(filenames) > 2:
        name += f" + {len(filenames) - 2} more"
    return name if len(name) <= MAX_NAME_LENGTH else name[: MAX_NAME_LENGTH - 1] + "…"


def _lock_set(db: Session, set_id: int) -> None:
    """Row-lock the set until commit/rollback so saves for it run one at a time."""
    db.query(MergedSet.id).filter(MergedSet.id == set_id).with_for_update().first()


def _lock_creation(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _CREATE_LOCK_KEY})


def _member_ids(db: Session, set_id: int) -> List[int]:
    return [
        row.document_id for row in
        db.query(MergedSetDocument.document_id).filter(MergedSetDocument.set_id == set_id)
        .order_by(MergedSetDocument.position.asc()).all()
    ]


def _find_same_set(db: Session, document_ids: List[int], user_id: int) -> Optional[int]:
    """The user's oldest set whose current members are exactly these documents, if any."""
    wanted = set(document_ids)
    candidates = (
        db.query(MergedSetDocument.set_id)
        .join(MergedSet, MergedSet.id == MergedSetDocument.set_id)
        .filter(MergedSetDocument.document_id.in_(wanted), MergedSet.user_id == user_id)
        .group_by(MergedSetDocument.set_id)
        .having(func.count(MergedSetDocument.document_id) == len(wanted))
        .order_by(MergedSetDocument.set_id.asc())
        .all()
    )
    for (set_id,) in candidates:
        if set(_member_ids(db, set_id)) == wanted:
            return set_id
    return None


def set_dicts(db: Session, sets: List[MergedSet]) -> List[dict]:
    """API shape for sets, with members, generated-content status and staleness."""
    if not sets:
        return []
    ids = [s.id for s in sets]
    members = (
        db.query(MergedSetDocument.set_id, Document.id, Document.filename, Document.source_type, Document.source_url)
        .join(Document, Document.id == MergedSetDocument.document_id)
        .filter(MergedSetDocument.set_id.in_(ids))
        .order_by(MergedSetDocument.set_id, MergedSetDocument.position)
        .all()
    )
    summaries = {
        row.set_id: row.document_ids for row in
        db.query(MergedSummary.set_id, MergedSummary.document_ids).filter(MergedSummary.set_id.in_(ids)).all()
    }
    cards = {
        row.set_id: (row.total, row.unlinked) for row in
        db.query(
            MergedFlashcard.set_id,
            func.count(MergedFlashcard.id).label("total"),
            func.count(MergedFlashcard.id).filter(MergedFlashcard.document_id.is_(None)).label("unlinked"),
        ).filter(MergedFlashcard.set_id.in_(ids)).group_by(MergedFlashcard.set_id).all()
    }

    by_set = {i: [] for i in ids}
    for row in members:
        by_set[row.set_id].append({
            "id": row.id, "filename": row.filename,
            "source_type": row.source_type or "pdf", "source_url": row.source_url,
        })

    result = []
    for s in sets:
        docs = by_set[s.id]
        current = {d["id"] for d in docs}
        summary_ids = json.loads(summaries[s.id]) if s.id in summaries else None
        total_cards, unlinked = cards.get(s.id, (0, 0))
        result.append({
            "id": s.id,
            "name": s.name,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "documents": docs,
            "has_summary": summary_ids is not None,
            "flashcard_count": total_cards,
            # Generated before one of its documents was deleted: regenerate to drop it.
            "summary_stale": summary_ids is not None and not set(summary_ids) <= current,
            "flashcards_stale": unlinked > 0,
        })
    return result


def _get_set(db: Session, set_id: int, user: User) -> MergedSet:
    """The user's set, or 404 (another user's set looks like a missing one)."""
    merged = db.query(MergedSet).filter(MergedSet.id == set_id, MergedSet.user_id == user.id).first()
    if not merged:
        raise HTTPException(status_code=404, detail="Merged set not found")
    return merged


@router.post("")
def create_merged_set(body: CreateMergedSetRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document_ids = list(dict.fromkeys(body.document_ids))  # drop repeats, keep selection order
    if len(document_ids) < MIN_DOCUMENTS:
        raise HTTPException(status_code=400, detail=f"Pick at least {MIN_DOCUMENTS} documents to merge.")
    if len(document_ids) > MAX_DOCUMENTS:
        raise HTTPException(status_code=400, detail=f"A merged set can have at most {MAX_DOCUMENTS} documents.")
    name = _clean_name(body.name) if body.name is not None else None

    docs = {
        row.id: row for row in
        db.query(Document.id, Document.filename, func.coalesce(func.length(Document.content), 0).label("chars"))
        .filter(Document.id.in_(document_ids), Document.user_id == user.id).all()
    }
    missing = [i for i in document_ids if i not in docs]
    if missing:
        raise HTTPException(status_code=404, detail=f"Document not found: {', '.join(map(str, missing))}")
    total_chars = sum(docs[i].chars for i in document_ids)
    if total_chars > MAX_TOTAL_CHARS:
        raise HTTPException(
            status_code=400,
            detail=(f"These documents have {total_chars:,} characters of text together; a merged set can have "
                    f"at most {MAX_TOTAL_CHARS:,}. Pick fewer or smaller documents."),
        )

    _lock_creation(db)
    existing_id = _find_same_set(db, document_ids, user.id)
    if existing_id is not None:
        db.commit()  # releases the lock
        return {"created": False, "merged_set": set_dicts(db, [_get_set(db, existing_id, user)])[0]}

    merged = MergedSet(name=name or default_set_name([docs[i].filename for i in document_ids]), user_id=user.id)
    merged.members = [MergedSetDocument(document_id=doc_id, position=pos) for pos, doc_id in enumerate(document_ids)]
    db.add(merged)
    db.commit()
    db.refresh(merged)
    return {"created": True, "merged_set": set_dicts(db, [merged])[0]}


@router.get("")
def list_merged_sets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sets = db.query(MergedSet).filter(MergedSet.user_id == user.id).order_by(MergedSet.created_at.desc(), MergedSet.id.desc()).all()
    return set_dicts(db, sets)


@router.get("/{set_id}")
def get_merged_set(set_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return set_dicts(db, [_get_set(db, set_id, user)])[0]


@router.patch("/{set_id}")
def rename_merged_set(set_id: int, body: RenameMergedSetRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    name = _clean_name(body.name)
    merged = _get_set(db, set_id, user)
    if name != merged.name:
        merged.name = name
        db.commit()
        db.refresh(merged)
    return set_dicts(db, [merged])[0]


@router.delete("/{set_id}")
def delete_merged_set(set_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Deletes the set with its merged summary and cards; its documents are untouched."""
    merged = _get_set(db, set_id, user)
    name = merged.name
    db.delete(merged)
    db.commit()
    return {"message": f"Merged set '{name}' deleted. Its documents were not changed.", "id": set_id}


# ─── Merged summary ───


def load_sources(db: Session, merged: MergedSet) -> List[MergedSource]:
    """The set's current documents, in set order, with their chunks and per-chunk citations.

    Sources are numbered 1..n over the current members, so after a member is
    deleted a regenerated summary numbers the rest without a gap (its sources
    list is rebuilt too). A document without chunks contributes its full text
    as one block, cited by source number only.
    """
    members = (
        db.query(MergedSetDocument.position, Document)
        .join(Document, Document.id == MergedSetDocument.document_id)
        .filter(MergedSetDocument.set_id == merged.id)
        .order_by(MergedSetDocument.position.asc())
        .all()
    )
    sources = []
    for number, (_, doc) in enumerate(members, start=1):
        rows = [
            c for c in db.query(Chunk).filter(Chunk.document_id == doc.id).order_by(Chunk.id.asc()).all()
            if c.content and c.content.strip()
        ]
        if rows:
            chunks = [c.content for c in rows]
            citations = build_chunk_citations(
                doc.source_type or "pdf", doc.source_url, doc.filename,
                [(c.content, c.start_seconds) for c in rows],
                pages=[(c.page_start, c.page_end) for c in rows],
            )
        else:
            chunks = [doc.content] if doc.content and doc.content.strip() else []
            citations = [None] * len(chunks)
        sources.append(MergedSource(
            number=number, title=doc.filename, source_type=doc.source_type or "pdf",
            source_url=doc.source_url, chunks=chunks, citations=citations, document_id=doc.id,
        ))
    return sources


def _summary_dict(merged: MergedSet, summary: MergedSummary, member_ids: List[int]) -> dict:
    ids = json.loads(summary.document_ids)
    return {
        "set_id": merged.id,
        "summary": summary.content,
        "created_at": summary.created_at.isoformat() if summary.created_at else None,
        "stale": not set(ids) <= set(member_ids),
    }


@router.post("/{set_id}/summary")
def create_merged_summary(
    set_id: int,
    regenerate: bool = Query(False, description="Replace the existing merged summary"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    merged = _get_set(db, set_id, user)
    existing = db.query(MergedSummary).filter(MergedSummary.set_id == set_id).first()
    if existing and not regenerate:
        return _summary_dict(merged, existing, _member_ids(db, set_id))

    sources = load_sources(db, merged)
    if len(sources) < MIN_DOCUMENTS:
        raise HTTPException(
            status_code=400,
            detail="This set has fewer than 2 documents left, so there's nothing to merge. "
                   "Create a new set from the Library instead.",
        )
    if not any(s.chunks for s in sources):
        raise HTTPException(status_code=400, detail="These documents have no text to summarize.")

    try:
        content = generate_merged_summary(sources)
    except AIGenerationError as e:
        detail = f"{e} The existing merged summary was not changed." if existing else str(e)
        raise HTTPException(status_code=502, detail=detail)

    # Same pattern as per-document summaries: lock only around the save, and
    # keep a summary another request saved meanwhile unless regenerating.
    _lock_set(db, set_id)
    existing = db.query(MergedSummary).filter(MergedSummary.set_id == set_id).first()
    used_ids = json.dumps([s.document_id for s in sources])
    if existing and not regenerate:
        db.commit()
    elif existing:
        existing.content = content
        existing.document_ids = used_ids
        existing.created_at = datetime.utcnow()
        db.commit()
    else:
        existing = MergedSummary(set_id=set_id, content=content, document_ids=used_ids)
        db.add(existing)
        db.commit()
    db.refresh(existing)
    return _summary_dict(merged, existing, _member_ids(db, set_id))


@router.get("/{set_id}/summary")
def get_merged_summary(set_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    merged = _get_set(db, set_id, user)
    summary = db.query(MergedSummary).filter(MergedSummary.set_id == set_id).first()
    if not summary:
        raise HTTPException(status_code=404, detail="No merged summary yet")
    return _summary_dict(merged, summary, _member_ids(db, set_id))


# ─── Merged flashcards ───


def _card_dict(card: MergedFlashcard) -> dict:
    return {
        "id": card.id,
        "question": card.question,
        "answer": card.answer,
        "source_label": card.source_label,
        "source_url": card.source_url,
        "document_id": card.document_id,
    }


def _deck_dict(set_id: int, cards: List[MergedFlashcard]) -> dict:
    return {
        "set_id": set_id,
        "flashcards": [_card_dict(c) for c in cards],
        # A card whose document was deleted keeps its text but loses its link.
        "stale": any(c.document_id is None for c in cards),
    }


def _saved_cards(db: Session, set_id: int) -> List[MergedFlashcard]:
    return db.query(MergedFlashcard).filter(MergedFlashcard.set_id == set_id).order_by(MergedFlashcard.id.asc()).all()


@router.post("/{set_id}/flashcards")
def create_merged_flashcards(
    set_id: int,
    count: int = Query(10, ge=1, le=50, description="Number of flashcards in the deck"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate the set's deck, replacing its previous merged deck only on success."""
    merged = _get_set(db, set_id, user)
    sources = load_sources(db, merged)
    if len(sources) < MIN_DOCUMENTS:
        raise HTTPException(
            status_code=400,
            detail="This set has fewer than 2 documents left, so there's nothing to merge. "
                   "Create a new set from the Library instead.",
        )
    if not any(s.chunks for s in sources):
        raise HTTPException(status_code=400, detail="These documents have no text to make flashcards from.")

    try:
        cards = generate_merged_flashcards(sources, count=count)
    except AIGenerationError as e:
        raise HTTPException(status_code=502, detail=f"{e} Your existing flashcards were not changed.")
    if not cards:
        raise HTTPException(
            status_code=502,
            detail="The AI didn't return any flashcards. Please try again. Your existing flashcards were not changed.",
        )

    # Lock only around the replace, as for per-document decks, so two
    # concurrent generations can't interleave their deletes and inserts.
    _lock_set(db, set_id)
    db.query(MergedFlashcard).filter(MergedFlashcard.set_id == set_id).delete()
    db.add_all([
        MergedFlashcard(
            set_id=set_id, document_id=c["document_id"], question=c["question"], answer=c["answer"],
            source_label=c["source_label"], source_url=c["source_url"],
        )
        for c in cards
    ])
    db.commit()
    return _deck_dict(set_id, _saved_cards(db, set_id))


@router.get("/{set_id}/flashcards")
def get_merged_flashcards(set_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_set(db, set_id, user)
    return _deck_dict(set_id, _saved_cards(db, set_id))
