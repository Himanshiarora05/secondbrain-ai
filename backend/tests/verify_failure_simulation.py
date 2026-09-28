"""
Failure simulation test:
1. Verifies that an AI generation failure (simulated via invalid API key / OpenAI error):
   (a) Returns HTTP 502 with a clear error message (not 500 or 200).
   (b) Leaves the existing saved Flashcard rows in Postgres completely untouched.
2. Restores the real API key and verifies normal generation works end-to-end.
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from fastapi.testclient import TestClient
from main import app
from app.database.db import SessionLocal
from app.models.document import Document
from app.models.flashcard import Flashcard
import app.services.ai.summary_service as summary_mod
import app.services.ai.flashcard_service as flashcard_mod

def run_simulation():
    real_api_key = os.getenv("OPENROUTER_API_KEY")
    assert real_api_key, "OPENROUTER_API_KEY is not set"

    client = TestClient(app)
    db = SessionLocal()
    try:
        # Find a document with content
        doc = db.query(Document).filter(Document.id == 2).first() or db.query(Document).first()
        assert doc is not None, "No document found in database"
        doc_id = doc.id

        # Ensure document has at least one saved flashcard to test data-preservation
        cards = db.query(Flashcard).filter(Flashcard.document_id == doc_id).all()
        if not cards:
            c = Flashcard(document_id=doc_id, question="Original Q", answer="Original A")
            db.add(c)
            db.commit()
            cards = db.query(Flashcard).filter(Flashcard.document_id == doc_id).all()

        original_card_ids = [c.id for c in cards]
        original_card_data = [(c.id, c.question, c.answer) for c in cards]
        print(f"Document ID {doc_id} ('{doc.filename}') has {len(original_card_ids)} saved flashcards: IDs {original_card_ids}")
    finally:
        db.close()

    # Step 1: Simulate failure by setting invalid API key
    print("\n--- Simulating AI Generation Failure (Invalid API Key) ---")
    summary_mod.client.api_key = "sk-invalid-test-failure-simulation"
    flashcard_mod.client.api_key = "sk-invalid-test-failure-simulation"

    # Step 2: Call flashcard generation endpoint while failing
    res = client.post(f"/api/v1/documents/{doc_id}/flashcards?count=5")
    print(f"Flashcards response status code: {res.status_code}")
    print(f"Flashcards response body: {res.text}")

    assert res.status_code == 502, f"Expected HTTP 502, got {res.status_code}"
    detail = res.json().get("detail", "")
    assert "Flashcard generation failed, your existing flashcards were not changed" in detail, \
        f"Unexpected detail: {detail}"
    print("[OK] Flashcard endpoint returned 502 with protective error message.")

    # Step 3: Call summary generation endpoint while failing
    sum_res = client.post(f"/api/v1/documents/{doc_id}/summary?regenerate=true")
    print(f"Summary response status code: {sum_res.status_code}")
    print(f"Summary response body: {sum_res.text}")
    assert sum_res.status_code == 502, f"Expected HTTP 502, got {sum_res.status_code}"
    print("[OK] Summary endpoint returned 502 on failure.")

    # Step 4: Verify that Flashcard table rows are completely UNTOUCHED
    print("\n--- Verifying Database State After Failure ---")
    db = SessionLocal()
    try:
        current_cards = db.query(Flashcard).filter(Flashcard.document_id == doc_id).order_by(Flashcard.id.asc()).all()
        current_card_data = [(c.id, c.question, c.answer) for c in current_cards]

        assert len(current_cards) == len(original_card_ids), \
            f"Expected {len(original_card_ids)} cards, found {len(current_cards)}"
        assert current_card_data == original_card_data, \
            f"Cards were modified! Original: {original_card_data}, Current: {current_card_data}"

        print(f"[OK] Verified: All {len(current_cards)} original flashcards remain 100% intact in database!")
    finally:
        db.close()

    # Step 5: Restore real API key and verify normal end-to-end generation
    print("\n--- Restoring Real API Key & Verifying Normal Generation ---")
    summary_mod.client.api_key = real_api_key
    flashcard_mod.client.api_key = real_api_key

    normal_res = client.post(f"/api/v1/documents/{doc_id}/flashcards?count=3")
    assert normal_res.status_code == 200, f"Expected 200, got {normal_res.status_code}: {normal_res.text}"
    new_cards = normal_res.json().get("flashcards", [])
    assert len(new_cards) > 0, "No new cards generated with real key"
    print(f"[OK] Normal generation succeeded! Generated {len(new_cards)} flashcards:")
    for card in new_cards:
        print(f"  - Q: {card['question']}")
        print(f"    A: {card['answer']}")

    # Verify DB now has the new cards
    db = SessionLocal()
    try:
        updated_cards = db.query(Flashcard).filter(Flashcard.document_id == doc_id).all()
        assert len(updated_cards) == len(new_cards)
        print(f"[OK] Database now successfully updated with {len(updated_cards)} new flashcards.")
    finally:
        db.close()

    print("\n========================================================")
    print("ALL FAILURE SIMULATION & RESTORATION TESTS PASSED 100%!")
    print("========================================================")

if __name__ == "__main__":
    run_simulation()
