"""
Live E2E Verification Script:
Performs the 8-step verification process requested by the user:
Step 1: Confirm real document in DB
Step 2: Generate 5 flashcards, record exact rows
Step 3: Simulate AI provider failure (invalid API key)
Step 4: POST flashcards -> assert 502 with clear message
Step 5: GET flashcards -> assert identical IDs, questions, answers
Step 6: POST summary?regenerate=true -> assert 502, GET summary -> assert unchanged
Step 7: Restore real API key
Step 8: POST flashcards -> assert 200 with new cards
"""

import sys
import os
import json
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
from app.models.summary import Summary
from app.models.flashcard import Flashcard
import app.services.ai.summary_service as summary_service
import app.services.ai.flashcard_service as flashcard_service

def run():
    client = TestClient(app)
    real_key = os.getenv("OPENROUTER_API_KEY")
    assert real_key and real_key != "your_openrouter_key_here", "Real OPENROUTER_API_KEY not found in .env"

    results = {}

    print("=================================================================")
    print("STEP 1: Checking real document in database")
    print("=================================================================")
    db = SessionLocal()
    try:
        # Select document 2 (Graph_PPT.pdf) or first document with content
        doc = db.query(Document).filter(Document.id == 2).first()
        if not doc or not doc.content:
            doc = db.query(Document).filter(Document.content != "").first()
        assert doc is not None, "No valid document found in database"
        doc_id = doc.id
        doc_filename = doc.filename
        content_len = len(doc.content)
        print(f"Using Document ID: {doc_id} ('{doc_filename}'), content length: {content_len} chars")
    finally:
        db.close()

    results["step1"] = {"doc_id": doc_id, "filename": doc_filename, "content_len": content_len}

    print("\n=================================================================")
    print("STEP 2: Generating initial flashcards (HTTP 200) & recording state")
    print("=================================================================")
    # Ensure real API key is active
    summary_service.client.api_key = real_key
    flashcard_service.client.api_key = real_key

    # Also make sure there is an initial summary for step 6
    client.post(f"/api/v1/documents/{doc_id}/summary")
    initial_summary_resp = client.get(f"/api/v1/documents/{doc_id}/summary")
    recorded_summary = initial_summary_resp.json().get("summary")

    step2_res = client.post(f"/api/v1/documents/{doc_id}/flashcards?count=5")
    print(f"Status Code: {step2_res.status_code}")
    print(f"Response Body:\n{json.dumps(step2_res.json(), indent=2)}")
    assert step2_res.status_code == 200, f"Expected 200, got {step2_res.status_code}"

    step2_data = step2_res.json()
    assert len(step2_data["flashcards"]) == 5, f"Expected 5 flashcards, got {len(step2_data['flashcards'])}"

    # Record exact rows from DB directly
    db = SessionLocal()
    try:
        cards = db.query(Flashcard).filter(Flashcard.document_id == doc_id).order_by(Flashcard.id.asc()).all()
        recorded_cards = [
            {"id": c.id, "question": c.question, "answer": c.answer}
            for c in cards
        ]
    finally:
        db.close()

    print(f"Recorded {len(recorded_cards)} flashcard rows in DB:")
    for c in recorded_cards:
        print(f"  ID {c['id']}: Q: {c['question'][:60]}... | A: {c['answer'][:60]}...")

    results["step2"] = {
        "status_code": step2_res.status_code,
        "body": step2_data,
        "recorded_cards": recorded_cards,
        "recorded_summary_prefix": recorded_summary[:120] if recorded_summary else None,
    }

    print("\n=================================================================")
    print("STEP 3: Simulating AI provider failure (invalid API key)")
    print("=================================================================")
    broken_key = "sk-or-v1-invalid-key-for-failure-simulation"
    summary_service.client.api_key = broken_key
    flashcard_service.client.api_key = broken_key
    print("OpenAI clients in summary_service and flashcard_service configured with broken key.")

    print("\n=================================================================")
    print("STEP 4: Calling POST flashcards?count=5 during simulated failure")
    print("=================================================================")
    step4_res = client.post(f"/api/v1/documents/{doc_id}/flashcards?count=5")
    print(f"Status Code: {step4_res.status_code}")
    print(f"Response Body:\n{step4_res.text}")

    assert step4_res.status_code == 502, f"Expected 502, got {step4_res.status_code}"
    step4_json = step4_res.json()
    assert "Flashcard generation failed, your existing flashcards were not changed" in step4_json.get("detail", "")

    results["step4"] = {
        "status_code": step4_res.status_code,
        "body": step4_json,
    }

    print("\n=================================================================")
    print("STEP 5: Calling GET flashcards & verifying data was NOT deleted")
    print("=================================================================")
    step5_res = client.get(f"/api/v1/documents/{doc_id}/flashcards")
    print(f"Status Code: {step5_res.status_code}")
    print(f"Response Body:\n{json.dumps(step5_res.json(), indent=2)}")

    assert step5_res.status_code == 200, f"Expected 200, got {step5_res.status_code}"
    step5_cards = step5_res.json().get("flashcards", [])

    assert len(step5_cards) == len(recorded_cards), f"Card count changed! Recorded {len(recorded_cards)}, found {len(step5_cards)}"
    for rec, curr in zip(recorded_cards, step5_cards):
        assert rec["id"] == curr["id"], f"Card ID changed: {rec['id']} vs {curr['id']}"
        assert rec["question"] == curr["question"], f"Question changed: {rec['question']} vs {curr['question']}"
        assert rec["answer"] == curr["answer"], f"Answer changed: {rec['answer']} vs {curr['answer']}"

    print("[PROVED] Flashcard rows in database are 100% IDENTICAL to Step 2. Zero data loss!")
    results["step5"] = {
        "status_code": step5_res.status_code,
        "cards_verified_count": len(step5_cards),
        "data_identical": True,
    }

    print("\n=================================================================")
    print("STEP 6: Calling POST summary?regenerate=true during simulated failure")
    print("=================================================================")
    step6_post_res = client.post(f"/api/v1/documents/{doc_id}/summary?regenerate=true")
    print(f"POST summary Status Code: {step6_post_res.status_code}")
    print(f"POST summary Response Body:\n{step6_post_res.text}")
    assert step6_post_res.status_code == 502, f"Expected 502, got {step6_post_res.status_code}"

    step6_get_res = client.get(f"/api/v1/documents/{doc_id}/summary")
    print(f"GET summary Status Code: {step6_get_res.status_code}")
    current_summary = step6_get_res.json().get("summary")
    assert current_summary == recorded_summary, "Summary was corrupted or lost during failed regeneration!"
    print("[PROVED] Summary in database is 100% UNCHANGED after failed regeneration!")

    results["step6"] = {
        "post_status_code": step6_post_res.status_code,
        "post_body": step6_post_res.json(),
        "get_status_code": step6_get_res.status_code,
        "summary_unchanged": True,
    }

    print("\n=================================================================")
    print("STEP 7: Restoring real API key")
    print("=================================================================")
    summary_service.client.api_key = real_key
    flashcard_service.client.api_key = real_key
    print("Real API key restored on both services.")

    print("\n=================================================================")
    print("STEP 8: Calling POST flashcards?count=5 to confirm recovery")
    print("=================================================================")
    step8_res = client.post(f"/api/v1/documents/{doc_id}/flashcards?count=5")
    print(f"Status Code: {step8_res.status_code}")
    print(f"Response Body:\n{json.dumps(step8_res.json(), indent=2)}")

    assert step8_res.status_code == 200, f"Expected 200, got {step8_res.status_code}"
    step8_cards = step8_res.json().get("flashcards", [])
    assert len(step8_cards) == 5, f"Expected 5 flashcards, got {len(step8_cards)}"
    new_ids = [c["id"] for c in step8_cards]
    old_ids = [c["id"] for c in recorded_cards]
    assert new_ids != old_ids, f"Expected new IDs after successful regeneration, got same IDs: {new_ids}"

    print(f"[PROVED] Recovery verified! Newly generated IDs: {new_ids} (previous IDs were: {old_ids})")
    results["step8"] = {
        "status_code": step8_res.status_code,
        "body": step8_res.json(),
        "new_ids": new_ids,
        "old_ids": old_ids,
    }

    print("\n=================================================================")
    print("ALL 8 VERIFICATION STEPS COMPLETED & VALIDATED WITH ZERO ERRORS!")
    print("=================================================================")

    # Write output to json file for reference
    with open("tests/verification_report.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    run()
