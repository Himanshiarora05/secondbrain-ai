import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from fastapi.testclient import TestClient
from main import app
from app.database.db import SessionLocal
from app.models.document import Document
from app.models.chunk import Chunk
from app.database.chroma import get_collection

client = TestClient(app)
db = SessionLocal()

# 1. Before counts
before_docs = db.query(Document).all()
before_count = len(before_docs)
print(f"Total documents before cleanup: {before_count}")

# Verify IDs 3-8 exist and are zero-chunk
target_ids = [3, 4, 5, 6, 7, 8]
for tid in target_ids:
    doc = db.query(Document).filter(Document.id == tid).first()
    assert doc is not None, f"Expected doc {tid} to exist"
    assert len(doc.chunks) == 0, f"Expected doc {tid} to have 0 chunks"
    print(f"Verified doc {tid} ({doc.filename}) has 0 chunks")

# 2. Call DELETE endpoint for IDs 3 to 8
for tid in target_ids:
    resp = client.delete(f"/api/v1/documents/{tid}")
    print(f"DELETE /api/v1/documents/{tid} -> Status: {resp.status_code}, Body: {resp.json()}")
    assert resp.status_code == 200, f"Failed to delete doc {tid}"

# 3. After counts
after_docs = db.query(Document).order_by(Document.id).all()
after_count = len(after_docs)
print(f"\nTotal documents after cleanup: {after_count}")
print(f"Difference: {before_count - after_count} documents removed")
assert after_count == before_count - len(target_ids), f"Expected {before_count - len(target_ids)}, got {after_count}"

# 4. Verify IDs 9 to 16 are completely intact and healthy
print("\nVerifying healthy documents (IDs 9-16) are untouched:")
col = get_collection()
for hid in range(9, 17):
    doc = db.query(Document).filter(Document.id == hid).first()
    assert doc is not None, f"Healthy doc {hid} missing!"
    chunks_count = len(doc.chunks)
    chroma_count = len(col.get(where={"document_id": hid})["ids"])
    print(f"  Healthy Doc {hid}: {doc.filename} | Postgres chunks: {chunks_count} | Chroma vectors: {chroma_count}")
    assert chunks_count == 23, f"Expected 23 chunks for doc {hid}"
    assert chroma_count == 23, f"Expected 23 chroma vectors for doc {hid}"

# 5. Verify zero orphaned vectors in Chroma for deleted IDs 3-8
print("\nVerifying zero orphaned Chroma vectors for deleted IDs 3-8:")
all_chroma_ids = col.get()["ids"]
for tid in target_ids:
    by_meta = col.get(where={"document_id": tid})["ids"]
    by_prefix = [cid for cid in all_chroma_ids if cid.startswith(f"{tid}-")]
    print(f"  Deleted Doc {tid}: vectors by metadata={len(by_meta)}, vectors by prefix={len(by_prefix)}")
    assert len(by_meta) == 0, f"Found orphaned vectors by metadata for doc {tid}: {by_meta}"
    assert len(by_prefix) == 0, f"Found orphaned vectors by prefix for doc {tid}: {by_prefix}"

# 6. Verify 404 on deleting non-existent document
resp_404 = client.delete("/api/v1/documents/999999")
assert resp_404.status_code == 404, f"Expected 404, got {resp_404.status_code}"
print("\nVerified 404 on non-existent document ID.")

db.close()
print("\nALL CLEANUP AND DELETE ENDPOINT CHECKS PASSED!")
