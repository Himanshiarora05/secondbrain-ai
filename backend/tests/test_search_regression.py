import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()
from fastapi.testclient import TestClient
from main import app
import json

client = TestClient(app)
response = client.get("/api/v1/search", params={"query": "graph algorithms vertex edge"})
print(f"STATUS CODE: {response.status_code}")
if response.status_code != 200:
    print(f"ERROR: {response.text}")
    sys.exit(1)

data = response.json()
print("QUERY:", data.get("query"))
print("TOP MATCHES COUNT:", len(data.get("top_matches", [])))
for i, m in enumerate(data.get("top_matches", [])):
    print(f"Match {i+1}:")
    print(f"  Document: {m.get('document')}")
    print(f"  Score: {m.get('score'):.4f}")
    print(f"  YouTube Timestamp URL: {m.get('youtube_timestamp_url')}")
    print(f"  Content length: {len(m.get('content', ''))}")
print("\nREGRESSION TEST PASSED: No ValueError, 4-tuples unpacked cleanly in app/routes/search.py!")
