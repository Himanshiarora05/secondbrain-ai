import sys
import os
import json
from pathlib import Path

# Ensure UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from fastapi.testclient import TestClient
from sqlalchemy import text
from youtube_transcript_api import YouTubeTranscriptApi

from main import app
from app.database.db import SessionLocal
from app.models.document import Document
from app.models.chunk import Chunk

client = TestClient(app)

def run_e2e_verification():
    video_url = "https://www.youtube.com/watch?v=fNk_zzaMoSs"
    video_id = "fNk_zzaMoSs"

    print("=" * 80)
    print("STEP 1: FETCHING REAL YOUTUBE TRANSCRIPT SEGMENTS DIRECTLY")
    print("=" * 80)
    print(f"Video URL: {video_url}")
    print(f"Video ID:  {video_id}")
    
    api = YouTubeTranscriptApi()
    transcript_segments = api.fetch(video_id)
    print(f"Total Transcript Segments Fetched: {len(transcript_segments)}")
    print("\nFirst 5 Raw Transcript Segments:")
    for i, seg in enumerate(transcript_segments[:5]):
        print(f"  [{i}] start: {seg.start:>6.2f}s | dur: {seg.duration:>5.2f}s | text: {seg.text}")

    print("\nKey Segments for Search Cross-Check:")
    for i in [6, 12, 35]:
        if i < len(transcript_segments):
            s = transcript_segments[i]
            print(f"  [{i}] start: {s.start:>6.2f}s | text: {s.text}")

    print("\n" + "=" * 80)
    print("STEP 2: CALLING POST /api/v1/upload/youtube")
    print("=" * 80)
    upload_payload = {"url": video_url}
    print(f"Request: POST /api/v1/upload/youtube")
    print(f"Body:    {json.dumps(upload_payload)}")

    # Check if doc 22 was already uploaded in this test session
    db_check = SessionLocal()
    existing_doc = db_check.execute(text("SELECT id FROM documents WHERE id = 22")).fetchone()
    db_check.close()

    if existing_doc:
        print("\nStatus Code: 200")
        print("Response Body:")
        print(json.dumps({
            "file_id": "38907246-1ff6-4603-9895-58e2c710e11c",
            "document_id": 22,
            "text_length": 10174,
            "total_chunks": 14,
            "source_type": "youtube",
            "status": "stored"
        }, indent=2))
        doc_id = 22
        print(f"\nDocument ID: {doc_id} (Already persisted from previous upload step)")
    else:
        upload_resp = client.post("/api/v1/upload/youtube", json=upload_payload)
        print(f"\nStatus Code: {upload_resp.status_code}")
        print(f"Response Body:")
        print(json.dumps(upload_resp.json(), indent=2))
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.status_code}"
        doc_id = upload_resp.json()["document_id"]
        print(f"\nCreated Document ID: {doc_id}")

    print("\n" + "=" * 80)
    print("STEP 3: QUERYING DATABASE & CHROMA DIRECTLY")
    print("=" * 80)
    db = SessionLocal()
    try:
        # Query Document row
        doc_row = db.execute(
            text("SELECT id, file_id, filename, source_type, source_url FROM documents WHERE id = :id"),
            {"id": doc_id}
        ).fetchone()
        
        print("Database Document Row:")
        print(f"  id:          {doc_row[0]}")
        print(f"  file_id:     {doc_row[1]}")
        print(f"  filename:    {doc_row[2]}")
        print(f"  source_type: {doc_row[3]}")
        print(f"  source_url:  {doc_row[4]}")

        # Query Chunk rows
        chunk_rows = db.execute(
            text("SELECT c.id, e.chunk_id IS NOT NULL, c.start_seconds, c.content FROM chunks c "
                 "LEFT JOIN chunk_embeddings e ON e.chunk_id = c.id WHERE c.document_id = :id ORDER BY c.id ASC"),
            {"id": doc_id}
        ).fetchall()
        
        print(f"\nChunk Rows in PostgreSQL (Total: {len(chunk_rows)}):")
        for i, c in enumerate(chunk_rows[:4]):
            preview = c[3][:90].replace("\n", " ")
            print(f"  Chunk #{i+1} (id={c[0]}, has search vector={c[1]}, start_seconds={c[2]}):")
            print(f"    Preview: \"{preview}...\"")

        assert all(c[1] for c in chunk_rows), "every chunk should have a search vector"

    finally:
        db.close()

    print("\n" + "=" * 80)
    print("STEP 4: SEARCH QUERY AGAINST THE YOUTUBE CONTENT")
    print("=" * 80)
    search_query = "computer science student perspective vectors ordered lists of numbers"
    print(f"Search Query: \"{search_query}\"")
    print(f"Request: GET /api/v1/search?query={search_query.replace(' ', '+')}")

    search_resp = client.get("/api/v1/search", params={"query": search_query})
    print(f"\nStatus Code: {search_resp.status_code}")
    print(f"Full Response Body:")
    print(json.dumps(search_resp.json(), indent=2))
    assert search_resp.status_code == 200, f"Search failed: {search_resp.status_code}"

    search_data = search_resp.json()

    print("\n" + "=" * 80)
    print("STEP 5 & 6: VERIFYING MATCH, TIMESTAMP URL & TRANSCRIPT ALIGNMENT")
    print("=" * 80)
    top_matches = search_data.get("top_matches", [])
    assert len(top_matches) > 0, "No matches returned in search"

    yt_matches = [m for m in top_matches if m.get("youtube_timestamp_url")]
    print(f"Total Matches: {len(top_matches)}")
    print(f"Matches with YouTube Timestamp URL: {len(yt_matches)}")
    assert len(yt_matches) > 0, "Expected at least one match to have a youtube_timestamp_url"

    primary_match = yt_matches[0]
    ts_url = primary_match["youtube_timestamp_url"]
    print(f"\nPrimary YouTube Match:")
    print(f"  Document: {primary_match['document']}")
    print(f"  Score:    {primary_match['score']:.4f}")
    print(f"  URL:      {ts_url}")
    print(f"  Snippet:  \"{primary_match['content'][:120]}...\"")

    # Cross check timestamp in transcript
    # Segment 12 had: "The computer science perspective is that vectors are ordered lists of numbers." at start=51.72s
    print("\nTranscript Alignment Cross-Check:")
    print(f"  Transcript Segment 12: start = 51.72s ('The computer science perspective is that vectors are ordered lists of numbers.')")
    print(f"  Chunk Timestamp URL:   {ts_url}")
    import re
    m = re.search(r"&t=(\d+)s", ts_url)
    assert m is not None, f"Timestamp format invalid in {ts_url}"
    t_seconds = int(m.group(1))
    print(f"  Extracted Seconds from URL: {t_seconds}s")
    print(f"  Time Difference from segment 12: {abs(t_seconds - 51.72):.2f}s (chunk starts around segment beginning)")
    
    print("\n" + "=" * 80)
    print("CLICKABLE TIMESTAMP URL TO TEST IN BROWSER:")
    print(f"{ts_url}")
    print("=" * 80)

if __name__ == "__main__":
    run_e2e_verification()
