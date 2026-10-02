"""Offline checks for spaced repetition: the SM-2 maths, rating cards, and the "due today" list.

Runs the route functions against an in-memory SQLite database (foreign keys on).
No Postgres, Chroma, network or AI.

Run from backend/:  .venv/Scripts/python.exe tests/test_spaced_repetition.py
"""
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database, vector store or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="sb-test-chroma-")
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base
from app.models import Document, Flashcard, MergedFlashcard, MergedSet, MergedSetDocument, User
from app.routes import review as rv
from app.routes import study, merged_sets
from app.routes.review import ReviewRequest
from app.services.spaced_repetition import review, local_today, MIN_EASE, MAX_INTERVAL_DAYS

TODAY = date(2026, 10, 2)


# ─── SM-2 maths ───


def test_new_card_intervals():
    good = review(2.5, 0, 0, "good", TODAY)
    assert (good.interval_days, good.repetitions, good.ease, good.due_date) == (1, 1, 2.5, TODAY + timedelta(days=1))
    second = review(good.ease, good.interval_days, good.repetitions, "good", TODAY)
    assert (second.interval_days, second.repetitions) == (6, 2)
    third = review(second.ease, second.interval_days, second.repetitions, "good", TODAY)
    assert (third.interval_days, third.repetitions) == (15, 3), third  # 6 * 2.5


def test_easy_is_always_later_than_good_and_raises_ease():
    for interval, reps in [(0, 0), (1, 1), (6, 2), (15, 3)]:
        good = review(2.5, interval, reps, "good", TODAY)
        easy = review(2.5, interval, reps, "easy", TODAY)
        assert easy.interval_days > good.interval_days, (interval, reps, good, easy)
        assert easy.ease == 2.6


def test_again_starts_over_and_stays_due_today():
    s = review(2.5, 15, 3, "again", TODAY)
    assert (s.interval_days, s.repetitions, s.due_date) == (0, 0, TODAY)
    assert s.ease == 2.18, s.ease  # 2.5 - 0.32
    after = review(s.ease, s.interval_days, s.repetitions, "good", TODAY)
    assert after.interval_days == 1, "relearning starts at 1 day again"


def test_ease_floor_and_interval_cap():
    ease = 2.5
    for _ in range(10):
        ease = review(ease, 0, 0, "again", TODAY).ease
    assert ease == MIN_EASE
    huge = review(2.5, 3000, 10, "easy", TODAY)
    assert huge.interval_days == MAX_INTERVAL_DAYS


def test_unknown_grade_is_refused():
    try:
        review(2.5, 0, 0, "hard", TODAY)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    try:
        ReviewRequest(grade="hard")
    except ValidationError:
        pass
    else:
        raise AssertionError("the API should refuse unknown grades")


def test_local_today_trusts_the_browser_within_a_day():
    assert local_today(TODAY + timedelta(days=1), TODAY) == TODAY + timedelta(days=1)
    assert local_today(TODAY - timedelta(days=1), TODAY) == TODAY - timedelta(days=1)
    assert local_today(TODAY + timedelta(days=5), TODAY) == TODAY, "implausible dates are ignored"
    assert local_today(None, TODAY) == TODAY


# ─── Routes ───


def fresh_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def add_user(db, email):
    user = User(email=email, password_hash="not-used")
    db.add(user)
    db.commit()
    return user


def add_deck(db, user, name, n=3, source_type="pdf"):
    doc = Document(user_id=user.id, file_id=f"f-{name}", filename=name, content="text", source_type=source_type)
    db.add(doc)
    db.commit()
    cards = [Flashcard(document_id=doc.id, question=f"{name} Q{i}", answer=f"A{i}") for i in range(n)]
    db.add_all(cards)
    db.commit()
    return doc, cards


def add_merged_deck(db, user, docs, n=2):
    s = MergedSet(name="Set", user_id=user.id)
    s.members = [MergedSetDocument(document_id=d.id, position=i) for i, d in enumerate(docs)]
    db.add(s)
    db.commit()
    cards = [MergedFlashcard(set_id=s.id, document_id=docs[0].id, question=f"M Q{i}", answer="A") for i in range(n)]
    db.add_all(cards)
    db.commit()
    return s, cards


def rate(db, user, kind, card_id, grade, today=TODAY):
    try:
        return rv.review_card(kind, card_id, ReviewRequest(grade=grade, today=today), db=db, user=user)
    except HTTPException as e:
        return e


def due(db, user, today=TODAY):
    return rv.due_cards(today=today, db=db, user=user)


def test_new_cards_have_defaults_and_are_due_from_the_start():
    db = fresh_db()
    alice = add_user(db, "alice@example.com")
    doc, cards = add_deck(db, alice, "cells.pdf")
    deck = study.get_document_flashcards(doc.id, db=db, user=alice)["flashcards"]
    assert all((c["ease"], c["interval_days"], c["repetitions"], c["due_date"]) == (2.5, 0, 0, None) for c in deck), deck
    listed = due(db, alice)
    assert [c["id"] for c in listed["cards"]] == [c.id for c in cards], "never-rated cards are due, in deck order"
    assert all(c["due_date"] is None for c in listed["cards"])
    assert rv.due_count(today=TODAY, db=db, user=alice)["count"] == 3


def test_rating_schedules_and_due_list_follows():
    db = fresh_db()
    alice = add_user(db, "alice@example.com")
    doc, cards = add_deck(db, alice, "cells.pdf")
    res = rate(db, alice, "document", cards[0].id, "good")
    assert res["due_date"] == (TODAY + timedelta(days=1)).isoformat() and res["repetitions"] == 1, res
    assert rate(db, alice, "document", cards[1].id, "again")["due_date"] == TODAY.isoformat()

    today_list = due(db, alice)
    assert [c["id"] for c in today_list["cards"]] == [cards[1].id, cards[2].id],         "the 'again' card, then the unrated one; the 'good' card waits until tomorrow"
    tomorrow = due(db, alice, TODAY + timedelta(days=1))
    assert [c["id"] for c in tomorrow["cards"]] == [cards[1].id, cards[0].id, cards[2].id], "oldest due first, new last"
    card = tomorrow["cards"][0]
    assert card["deck_name"] == "cells.pdf" and card["deck_id"] == doc.id and card["deck_source_type"] == "pdf"
    assert rv.due_count(today=TODAY + timedelta(days=1), db=db, user=alice)["count"] == 3
    assert rv.due_count(today=TODAY, db=db, user=alice)["count"] == 2

    # The deck shows the schedule too.
    deck = {c["id"]: c for c in study.get_document_flashcards(doc.id, db=db, user=alice)["flashcards"]}
    assert deck[cards[0].id]["interval_days"] == 1 and deck[cards[0].id]["last_reviewed_at"]


def test_merged_cards_are_rated_and_listed_with_their_set():
    db = fresh_db()
    alice = add_user(db, "alice@example.com")
    a, _ = add_deck(db, alice, "a.pdf", n=1)
    b, _ = add_deck(db, alice, "b.pptx", n=1, source_type="pptx")
    s, mcards = add_merged_deck(db, alice, [a, b])
    assert rate(db, alice, "merged", mcards[0].id, "good")["interval_days"] == 1
    assert rate(db, alice, "merged", mcards[0].id, "again", today=TODAY)["interval_days"] == 0
    merged_due = [c for c in due(db, alice)["cards"] if c["kind"] == "merged"]
    assert [c["id"] for c in merged_due] == [mcards[0].id, mcards[1].id], merged_due
    listed = merged_due
    assert listed[0]["deck_name"] == "Set"
    assert listed[0]["deck_source_type"] == "merged" and listed[0]["deck_id"] == s.id
    deck = merged_sets.get_merged_flashcards(s.id, db=db, user=alice)["flashcards"]
    assert deck[0]["due_date"] == TODAY.isoformat()
    # A document card id is not a merged card id.
    res = rate(db, alice, "document", mcards[1].id + 1000, "good")
    assert isinstance(res, HTTPException) and res.status_code == 404


def test_due_list_mixes_both_kinds_oldest_first():
    db = fresh_db()
    alice = add_user(db, "alice@example.com")
    doc, cards = add_deck(db, alice, "cells.pdf", n=2)
    other, _ = add_deck(db, alice, "genes.pdf", n=1)
    s, mcards = add_merged_deck(db, alice, [doc, other], n=1)
    rate(db, alice, "document", cards[0].id, "good", today=TODAY)                       # due TODAY+1
    rate(db, alice, "merged", mcards[0].id, "again", today=TODAY - timedelta(days=1))  # overdue since yesterday
    listed = due(db, alice, TODAY + timedelta(days=1))["cards"]
    scheduled = [(c["kind"], c["id"]) for c in listed if c["due_date"]]
    assert scheduled == [("merged", mcards[0].id), ("document", cards[0].id)], listed
    assert all(c["due_date"] is None for c in listed[2:]) and len(listed) == 4, "the two unrated cards come last"


def test_other_users_cards_look_missing_and_never_show():
    db = fresh_db()
    alice, bob = add_user(db, "alice@example.com"), add_user(db, "bob@example.com")
    doc, cards = add_deck(db, alice, "cells.pdf")
    other, _ = add_deck(db, alice, "genes.pdf", n=1)
    s, mcards = add_merged_deck(db, alice, [doc, other])
    rate(db, alice, "document", cards[0].id, "again")
    for kind, cid in (("document", cards[0].id), ("merged", mcards[0].id)):
        res = rate(db, bob, kind, cid, "easy")
        missing = rate(db, bob, kind, 999_999, "easy")
        assert isinstance(res, HTTPException) and res.status_code == 404 and res.detail == missing.detail
    assert due(db, bob)["count"] == 0 and rv.due_count(today=TODAY, db=db, user=bob)["count"] == 0
    assert db.get(Flashcard, cards[0].id).repetitions == 0, "Bob's rating changed nothing"
    assert db.get(Flashcard, cards[0].id).due_date == TODAY


def test_deleting_a_document_removes_its_due_cards():
    db = fresh_db()
    alice = add_user(db, "alice@example.com")
    doc, cards = add_deck(db, alice, "cells.pdf")
    rate(db, alice, "document", cards[0].id, "again")
    assert due(db, alice)["count"] == 3
    db.delete(db.get(Document, doc.id))
    db.commit()
    assert due(db, alice)["count"] == 0


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
