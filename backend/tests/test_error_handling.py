import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app
from app.database.db import SessionLocal
from app.models.document import Document
from app.models.flashcard import Flashcard
from app.services.ai.summary_service import AIGenerationError

def test_ai_generation_error_handling():
    client = TestClient(app)
    db = SessionLocal()
    try:
        doc = db.query(Document).first()
        assert doc is not None, "Need at least one document in DB"
        doc_id = doc.id

        # Seed a dummy flashcard if none exists to test safe preservation
        existing_card = db.query(Flashcard).filter(Flashcard.document_id == doc_id).first()
        if not existing_card:
            existing_card = Flashcard(document_id=doc_id, question="Seed Q", answer="Seed A")
            db.add(existing_card)
            db.commit()
            db.refresh(existing_card)
        initial_card_count = db.query(Flashcard).filter(Flashcard.document_id == doc_id).count()
        assert initial_card_count > 0
    finally:
        db.close()

    print(f"Testing document ID {doc_id} with {initial_card_count} existing flashcards...")

    # 1. Test AIGenerationError handling in summary endpoint
    with patch("app.routes.study.generate_summary", side_effect=AIGenerationError("OpenAI timeout")):
        res = client.post(f"/api/v1/documents/{doc_id}/summary?regenerate=true")
        assert res.status_code == 502, f"Expected 502, got {res.status_code}"
        assert res.json()["detail"] == "AI generation failed, please try again"
        print("[OK] Summary endpoint gracefully returns 502 on AIGenerationError")

    # 2. Test AIGenerationError handling in flashcards endpoint
    with patch("app.routes.study.generate_flashcards", side_effect=AIGenerationError("OpenAI connection error")):
        res = client.post(f"/api/v1/documents/{doc_id}/flashcards?count=5")
        assert res.status_code == 502, f"Expected 502, got {res.status_code}"
        assert res.json()["detail"] == "AI generation failed, please try again"
        print("[OK] Flashcard endpoint gracefully returns 502 on AIGenerationError")

    # 3. Test empty cards_data handling and safe preservation of existing cards
    with patch("app.routes.study.generate_flashcards", return_value=[]):
        res = client.post(f"/api/v1/documents/{doc_id}/flashcards?count=5")
        assert res.status_code == 502, f"Expected 502, got {res.status_code}"
        assert res.json()["detail"] == "Flashcard generation failed - your existing flashcards were not changed"
        print("[OK] Flashcard endpoint returns 502 and clear message when cards_data is empty")

    # Verify that existing flashcards were NOT deleted
    db = SessionLocal()
    try:
        final_card_count = db.query(Flashcard).filter(Flashcard.document_id == doc_id).count()
        assert final_card_count == initial_card_count, f"Card count changed from {initial_card_count} to {final_card_count}"
        print(f"[OK] Existing flashcards preserved intact ({final_card_count} cards remain)")
    finally:
        db.close()

    print("ALL ERROR HANDLING TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_ai_generation_error_handling()
