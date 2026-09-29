"""
Merged sets: 2-8 documents studied together (see app/models/merged_set.py).

A set is created from a selection in the Library. Creating one with exactly
the documents of an existing set returns that set instead of a copy.
"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.document import Document
from app.models.merged_set import MergedFlashcard, MergedSet, MergedSetDocument, MergedSummary
from app.routes.documents import MAX_NAME_LENGTH

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


def _find_same_set(db: Session, document_ids: List[int]) -> Optional[int]:
    """The oldest set whose current members are exactly these documents, if any."""
    wanted = set(document_ids)
    candidates = (
        db.query(MergedSetDocument.set_id)
        .filter(MergedSetDocument.document_id.in_(wanted))
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


def _get_set(db: Session, set_id: int) -> MergedSet:
    merged = db.query(MergedSet).filter(MergedSet.id == set_id).first()
    if not merged:
        raise HTTPException(status_code=404, detail="Merged set not found")
    return merged


@router.post("")
def create_merged_set(body: CreateMergedSetRequest, db: Session = Depends(get_db)):
    document_ids = list(dict.fromkeys(body.document_ids))  # drop repeats, keep selection order
    if len(document_ids) < MIN_DOCUMENTS:
        raise HTTPException(status_code=400, detail=f"Pick at least {MIN_DOCUMENTS} documents to merge.")
    if len(document_ids) > MAX_DOCUMENTS:
        raise HTTPException(status_code=400, detail=f"A merged set can have at most {MAX_DOCUMENTS} documents.")
    name = _clean_name(body.name) if body.name is not None else None

    docs = {
        row.id: row for row in
        db.query(Document.id, Document.filename, func.coalesce(func.length(Document.content), 0).label("chars"))
        .filter(Document.id.in_(document_ids)).all()
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
    existing_id = _find_same_set(db, document_ids)
    if existing_id is not None:
        db.commit()  # releases the lock
        return {"created": False, "merged_set": set_dicts(db, [_get_set(db, existing_id)])[0]}

    merged = MergedSet(name=name or default_set_name([docs[i].filename for i in document_ids]))
    merged.members = [MergedSetDocument(document_id=doc_id, position=pos) for pos, doc_id in enumerate(document_ids)]
    db.add(merged)
    db.commit()
    db.refresh(merged)
    return {"created": True, "merged_set": set_dicts(db, [merged])[0]}


@router.get("")
def list_merged_sets(db: Session = Depends(get_db)):
    sets = db.query(MergedSet).order_by(MergedSet.created_at.desc(), MergedSet.id.desc()).all()
    return set_dicts(db, sets)


@router.get("/{set_id}")
def get_merged_set(set_id: int, db: Session = Depends(get_db)):
    return set_dicts(db, [_get_set(db, set_id)])[0]


@router.patch("/{set_id}")
def rename_merged_set(set_id: int, body: RenameMergedSetRequest, db: Session = Depends(get_db)):
    name = _clean_name(body.name)
    merged = _get_set(db, set_id)
    if name != merged.name:
        merged.name = name
        db.commit()
        db.refresh(merged)
    return set_dicts(db, [merged])[0]


@router.delete("/{set_id}")
def delete_merged_set(set_id: int, db: Session = Depends(get_db)):
    """Deletes the set with its merged summary and cards; its documents are untouched."""
    merged = _get_set(db, set_id)
    name = merged.name
    db.delete(merged)
    db.commit()
    return {"message": f"Merged set '{name}' deleted. Its documents were not changed.", "id": set_id}
