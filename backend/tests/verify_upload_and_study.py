"""
End-to-end test: upload a real PDF through /api/v1/upload/pdf, then generate
summary and flashcards for the newly created document.
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
from app.database.db import SessionLocal
from app.models.document import Document

def test_upload_and_study():
    client = TestClient(app)

    # Pick an existing pdf file in uploads to test the upload endpoint
    upload_dir = Path(__file__).resolve().parent.parent / "uploads"
    pdf_files = list(upload_dir.glob("*.pdf"))
    if not pdf_files:
        print("No sample PDF files found in uploads/")
        return

    sample_pdf = pdf_files[0]
    print(f"Uploading real PDF: {sample_pdf.name} ({sample_pdf.stat().st_size} bytes)...")

    with open(sample_pdf, "rb") as f:
        response = client.post(
            "/api/v1/upload/pdf",
            files={"file": ("test_fresh_upload.pdf", f, "application/pdf")},
        )

    assert response.status_code == 200, f"Upload failed: {response.status_code} {response.text}"
    upload_data = response.json()
    file_id = upload_data["file_id"]
    print(f"[OK] Upload succeeded! file_id: {file_id}, total_chunks: {upload_data['total_chunks']}")

    # Find the document id in the database
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.file_id == file_id).first()
        assert doc is not None, "Uploaded document not found in DB"
        doc_id = doc.id
    finally:
        db.close()

    print(f"[OK] Found newly created Document ID: {doc_id}")

    # Generate summary for newly uploaded document
    print("Generating summary for newly uploaded document...")
    sum_resp = client.post(f"/api/v1/documents/{doc_id}/summary")
    assert sum_resp.status_code == 200, f"Summary failed: {sum_resp.status_code} {sum_resp.text}"
    sum_data = sum_resp.json()
    print(f"[OK] Generated summary ({len(sum_data['summary'])} chars):")
    print(f"{sum_data['summary'][:250]}...\n")

    # Generate flashcards for newly uploaded document
    print("Generating flashcards for newly uploaded document...")
    fc_resp = client.post(f"/api/v1/documents/{doc_id}/flashcards?count=4")
    assert fc_resp.status_code == 200, f"Flashcards failed: {fc_resp.status_code} {fc_resp.text}"
    fc_data = fc_resp.json()
    print(f"[OK] Generated {len(fc_data['flashcards'])} flashcards:")
    for i, c in enumerate(fc_data["flashcards"]):
        print(f"  [{i+1}] Q: {c['question']}")
        print(f"      A: {c['answer']}")

    print("\n[OK] Complete end-to-end ingestion -> summary -> flashcards verified successfully!")

if __name__ == "__main__":
    test_upload_and_study()
