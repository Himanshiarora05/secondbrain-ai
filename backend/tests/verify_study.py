"""
Verification test script for SecondBrain AI Study features:
AI Summary (with map-reduce) and AI Flashcards.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from fastapi.testclient import TestClient
from main import app
from app.database.db import SessionLocal, init_db
from app.models.document import Document
from app.models.summary import Summary
from app.models.flashcard import Flashcard

def run_tests():
    print("=== 1. Testing DB Initialization ===")
    init_db()
    db = SessionLocal()
    try:
        docs = db.query(Document).all()
        print(f"Found {len(docs)} documents in database.")
        if not docs:
            print("ERROR: No documents found in database.")
            return False

        # Pick a short document and a long document (>6000 chars)
        short_doc = next((d for d in docs if 500 < len(d.content or '') < 5000), docs[0])
        long_doc = next((d for d in docs if len(d.content or '') > 6000), None)

        print(f"Selected short document: ID={short_doc.id}, name='{short_doc.filename}', length={len(short_doc.content)} chars")
        if long_doc:
            print(f"Selected long document: ID={long_doc.id}, name='{long_doc.filename}', length={len(long_doc.content)} chars")
    finally:
        db.close()

    client = TestClient(app)

    print("\n=== 2. Testing 404 for non-existent document ===")
    res = client.get("/api/v1/documents/999999/summary")
    assert res.status_code == 404, f"Expected 404, got {res.status_code}"
    print("[OK] 404 correctly returned for non-existent document summary")

    print("\n=== 3. Testing POST /api/v1/documents/{id}/summary (AI generation) ===")
    res = client.post(f"/api/v1/documents/{short_doc.id}/summary?regenerate=true")
    assert res.status_code == 200, f"Generate summary failed: {res.status_code} {res.text}"
    data = res.json()
    assert "summary" in data and len(data["summary"]) > 50, "Summary is empty or invalid"
    print(f"[OK] Summary generated successfully ({len(data['summary'])} chars)")
    print(f"Sample summary:\n{data['summary'][:300]}...\n")

    print("\n=== 4. Testing GET /api/v1/documents/{id}/summary (Retrieval) ===")
    res = client.get(f"/api/v1/documents/{short_doc.id}/summary")
    assert res.status_code == 200, f"Get summary failed: {res.status_code} {res.text}"
    get_data = res.json()
    assert get_data["summary"] == data["summary"], "Retrieved summary does not match generated summary"
    print("[OK] Saved summary retrieved from DB accurately")

    print("\n=== 5. Testing POST /api/v1/documents/{id}/flashcards?count=5 ===")
    res = client.post(f"/api/v1/documents/{short_doc.id}/flashcards?count=5")
    assert res.status_code == 200, f"Generate flashcards failed: {res.status_code} {res.text}"
    fc_data = res.json()
    assert "flashcards" in fc_data, "No flashcards in response"
    cards = fc_data["flashcards"]
    assert len(cards) > 0, "Zero flashcards returned"
    print(f"[OK] Generated {len(cards)} flashcards:")
    for i, c in enumerate(cards[:3]):
        print(f"  [{i+1}] Q: {c['question']}")
        print(f"      A: {c['answer']}")

    print("\n=== 6. Testing GET /api/v1/documents/{id}/flashcards ===")
    res = client.get(f"/api/v1/documents/{short_doc.id}/flashcards")
    assert res.status_code == 200, f"Get flashcards failed: {res.status_code} {res.text}"
    saved_cards = res.json()["flashcards"]
    assert len(saved_cards) == len(cards), f"Expected {len(cards)} cards, got {len(saved_cards)}"
    print(f"[OK] Retrieved {len(saved_cards)} flashcards from DB")

    if long_doc:
        print("\n=== 7. Testing Map-Reduce on Long Document (>6000 chars) ===")
        res = client.post(f"/api/v1/documents/{long_doc.id}/summary?regenerate=true")
        assert res.status_code == 200, f"Long doc summary failed: {res.status_code} {res.text}"
        long_summary = res.json()["summary"]
        assert len(long_summary) > 50, "Long summary is empty"
        print(f"[OK] Map-reduce summary generated successfully ({len(long_summary)} chars):")
        print(f"{long_summary[:350]}...\n")

        res = client.post(f"/api/v1/documents/{long_doc.id}/flashcards?count=5")
        assert res.status_code == 200, f"Long doc flashcards failed: {res.status_code} {res.text}"
        long_fc = res.json()["flashcards"]
        assert len(long_fc) > 0, "Long doc flashcards empty"
        print(f"[OK] Long doc map-reduce flashcards ({len(long_fc)} cards) generated successfully")

    print("\n==========================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==========================================")
    return True

if __name__ == "__main__":
    run_tests()
