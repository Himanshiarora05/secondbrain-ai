import sys
import os
import json
from pathlib import Path

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from fastapi.testclient import TestClient
from sqlalchemy import text
from main import app
from app.database.db import SessionLocal

client = TestClient(app)

def get_current_document_count(db):
    res = db.execute(text("SELECT COUNT(*) FROM documents")).scalar()
    return res

def get_latest_documents(db, limit=3):
    rows = db.execute(text("SELECT id, filename, source_type FROM documents ORDER BY id DESC LIMIT :limit"), {"limit": limit}).fetchall()
    return [{"id": r[0], "filename": r[1], "source_type": r[2]} for r in rows]

def run_negative_tests():
    db = SessionLocal()
    initial_count = get_current_document_count(db)
    print("=" * 70)
    print("NEGATIVE & ERROR-PATH LIVE VERIFICATION SUITE")
    print(f"Initial Document Count in Database: {initial_count}")
    print("=" * 70)

    # -------------------------------------------------------------
    # CASE 1: YOUTUBE - NO CAPTIONS / UNAVAILABLE
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print("CASE 1: YOUTUBE - NO CAPTIONS (Real video without English captions)")
    print("-" * 70)
    before_count = get_current_document_count(db)
    # 9bZkp7q19f0 is a real video with no English captions/transcript (raises NoTranscriptFound)
    yt_url_no_captions = "https://www.youtube.com/watch?v=9bZkp7q19f0"
    payload_1 = {"url": yt_url_no_captions}
    print(f"Request: POST /api/v1/upload/youtube")
    print(f"Payload: {json.dumps(payload_1)}")
    
    resp_1 = client.post("/api/v1/upload/youtube", json=payload_1)
    after_count = get_current_document_count(db)
    
    print(f"Status Code: {resp_1.status_code}")
    print(f"Response Body: {resp_1.text}")
    print(f"Database Document Count: Before = {before_count}, After = {after_count}")
    print(f"Document Row Created: {after_count > before_count}")

    # Subtest 1b: Unavailable / non-existent video ID
    print("\nSubtest 1b: Unavailable/invalid video ID")
    payload_1b = {"url": "https://www.youtube.com/watch?v=invalid_id_9999"}
    resp_1b = client.post("/api/v1/upload/youtube", json=payload_1b)
    after_count_1b = get_current_document_count(db)
    print(f"Status Code: {resp_1b.status_code}")
    print(f"Response Body: {resp_1b.text}")
    print(f"Database Document Count: After = {after_count_1b}")

    # -------------------------------------------------------------
    # CASE 2: YOUTUBE - INVALID / GARBAGE URL
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print("CASE 2: YOUTUBE - INVALID / GARBAGE URL")
    print("-" * 70)
    before_count = get_current_document_count(db)
    bad_url = "https://example.com/notyoutube"
    payload_2 = {"url": bad_url}
    print(f"Request: POST /api/v1/upload/youtube")
    print(f"Payload: {json.dumps(payload_2)}")

    resp_2 = client.post("/api/v1/upload/youtube", json=payload_2)
    after_count = get_current_document_count(db)

    print(f"Status Code: {resp_2.status_code}")
    print(f"Response Body: {resp_2.text}")
    print(f"Database Document Count: Before = {before_count}, After = {after_count}")
    print(f"Document Row Created: {after_count > before_count}")

    # Also test completely unparseable string like "not a url"
    payload_2b = {"url": "not a url"}
    print(f"\nSubtest 2b: Malformed string 'not a url'")
    resp_2b = client.post("/api/v1/upload/youtube", json=payload_2b)
    after_count_2b = get_current_document_count(db)
    print(f"Status Code: {resp_2b.status_code}")
    print(f"Response Body: {resp_2b.text}")
    print(f"Database Document Count: After = {after_count_2b}")

    # -------------------------------------------------------------
    # CASE 3: CORRUPTED PPTX
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print("CASE 3: CORRUPTED PPTX FILE")
    print("-" * 70)
    before_count = get_current_document_count(db)
    corrupted_pptx_bytes = b"NOT A VALID PPTX FILE - Plain text content simulating corruption"
    print(f"Request: POST /api/v1/upload/pptx")
    print(f"File Name: corrupt_presentation.pptx (Size: {len(corrupted_pptx_bytes)} bytes)")

    resp_3 = client.post(
        "/api/v1/upload/pptx",
        files={
            "file": (
                "corrupt_presentation.pptx",
                corrupted_pptx_bytes,
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
    )
    after_count = get_current_document_count(db)

    print(f"Status Code: {resp_3.status_code}")
    print(f"Response Body: {resp_3.text}")
    print(f"Database Document Count: Before = {before_count}, After = {after_count}")
    print(f"Document Row Created: {after_count > before_count}")

    # -------------------------------------------------------------
    # CASE 4: CORRUPTED DOCX
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print("CASE 4: CORRUPTED DOCX FILE")
    print("-" * 70)
    before_count = get_current_document_count(db)
    corrupted_docx_bytes = b"NOT A VALID DOCX FILE - Plain text content simulating corruption"
    print(f"Request: POST /api/v1/upload/docx")
    print(f"File Name: corrupt_document.docx (Size: {len(corrupted_docx_bytes)} bytes)")

    resp_4 = client.post(
        "/api/v1/upload/docx",
        files={
            "file": (
                "corrupt_document.docx",
                corrupted_docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    after_count = get_current_document_count(db)

    print(f"Status Code: {resp_4.status_code}")
    print(f"Response Body: {resp_4.text}")
    print(f"Database Document Count: Before = {before_count}, After = {after_count}")
    print(f"Document Row Created: {after_count > before_count}")

    # -------------------------------------------------------------
    # CASE 5: OVERSIZED FILE (>20MB)
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print("CASE 5: OVERSIZED FILE (>20MB)")
    print("-" * 70)
    before_count = get_current_document_count(db)
    oversized_size = 21 * 1024 * 1024  # 21MB
    print(f"Request: POST /api/v1/upload/pptx")
    print(f"File Name: oversized_slides.pptx (Size: {oversized_size / (1024*1024):.1f} MB)")
    
    # Generate 21MB dummy payload
    oversized_bytes = b"0" * oversized_size

    resp_5 = client.post(
        "/api/v1/upload/pptx",
        files={
            "file": (
                "oversized_slides.pptx",
                oversized_bytes,
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
    )
    after_count = get_current_document_count(db)

    print(f"Status Code: {resp_5.status_code}")
    print(f"Response Body: {resp_5.text}")
    print(f"Database Document Count: Before = {before_count}, After = {after_count}")
    print(f"Document Row Created: {after_count > before_count}")

    # Also test /upload/docx with oversized file to confirm consistency
    print(f"\nSubtest 5b: Oversized DOCX upload to /upload/docx")
    resp_5b = client.post(
        "/api/v1/upload/docx",
        files={
            "file": (
                "oversized_doc.docx",
                oversized_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    after_count_5b = get_current_document_count(db)
    print(f"Status Code: {resp_5b.status_code}")
    print(f"Response Body: {resp_5b.text}")
    print(f"Database Document Count: After = {after_count_5b}")

    # Final summary check
    final_count = get_current_document_count(db)
    print("\n" + "=" * 70)
    print("FINAL DATABASE AUDIT")
    print(f"Initial Count: {initial_count}")
    print(f"Final Count:   {final_count}")
    print(f"Net Row Change: {final_count - initial_count}")
    print("Recent Documents in Database:")
    for d in get_latest_documents(db, limit=5):
        print(f"  ID: {d['id']:<3} | source_type: {d['source_type']:<8} | filename: {d['filename']}")
    print("=" * 70)

    db.close()

if __name__ == "__main__":
    run_negative_tests()
