from fastapi import APIRouter, Query
from app.services.search_service import search_similar_chunks, generate_answer

router = APIRouter(prefix="/api/v1", tags=["Search"])


@router.get("/search")
def search(query: str = Query(...)):

    # 🔹 Step 1: Get similar chunks
    # (score, content, doc_name, youtube_timestamp_url, source_type, source_url)
    results = search_similar_chunks(query)[:3]

    # 🔹 Step 2: Build clean context (IMPORTANT)
    context = "\n\n".join([r[1] for r in results])

    # 🔹 Step 3: Generate AI answer
    answer = generate_answer(query, context)

    # 🔹 Step 4: Return clean response
    return {
        "query": query,
        "answer": answer,
        "top_matches": [
            {
                "score": score,
                "content": content,
                "document": doc_name,
                "youtube_timestamp_url": youtube_url,
                "source_type": source_type,
                "source_url": source_url,
            }
            for score, content, doc_name, youtube_url, source_type, source_url in results
        ],
    }
