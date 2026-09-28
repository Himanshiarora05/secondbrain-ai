import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from app.database.db import SessionLocal
from app.models.chunk import Chunk
from app.database.chroma import get_collection

db = SessionLocal()
c1 = db.query(Chunk).filter(Chunk.document_id == 1).count()
c2 = db.query(Chunk).filter(Chunk.document_id == 2).count()
print(f"Doc 1 chunks in DB: {c1}")
print(f"Doc 2 chunks in DB: {c2}")

col = get_collection()
v1 = len(col.get(where={"document_id": 1})["ids"])
v2 = len(col.get(where={"document_id": 2})["ids"])
print(f"Doc 1 vectors in Chroma: {v1}")
print(f"Doc 2 vectors in Chroma: {v2}")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

res1 = client.get("/api/v1/search", params={"query": "data structures linked list stack queue"}).json()
print("Search 1 (data structures) results:")
found1 = False
for m in res1.get("top_matches", []):
    print(f"  Doc {m.get('document')}: score={m.get('score'):.4f}")
    if "ds flabfile.pdf" in m.get("document", ""):
        found1 = True

res2 = client.get("/api/v1/search", params={"query": "graph vertex edge adjacency matrix"}).json()
print("Search 2 (graph) results:")
found2 = False
for m in res2.get("top_matches", []):
    print(f"  Doc {m.get('document')}: score={m.get('score'):.4f}")
    if "Graph_PPT.pdf" in m.get("document", ""):
        found2 = True

db.close()

if found1 and found2:
    print("\nSUCCESS: Both Doc 1 (ds flabfile.pdf) and Doc 2 (Graph_PPT.pdf) were successfully returned in search!")
else:
    print(f"\nResult: found1={found1}, found2={found2}")

