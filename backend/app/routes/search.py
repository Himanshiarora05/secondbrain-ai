from fastapi import APIRouter, Query
from app.services.search_service import search_similar_chunks, generate_answer

router = APIRouter(prefix="/api/v1", tags=["Search"])


@router.get("/search")
def search(query: str = Query(...)):
    
    # 🔹 Step 1: Get similar chunks (4-tuple: score, content, doc_name, youtube_timestamp_url)
    results = search_similar_chunks(query)

    # 🔹 Step 2: Build clean context (IMPORTANT)
    context = "\n\n".join([content for score, content, doc_name, youtube_url in results[:3]])

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
            }
            for score, content, doc_name, youtube_url in results[:3]
        ],
    }



    