from fastapi import APIRouter, HTTPException, Query
from app.services.search_service import search_similar_chunks, generate_answer
from app.services.ai.summary_service import AIGenerationError

router = APIRouter(prefix="/api/v1", tags=["Search"])


@router.get("/search")
def search(query: str = Query(...)):

    # 🔹 Step 1: Get similar chunks
    # (score, content, doc_name, youtube_timestamp_url, source_type, source_url, location)
    results = search_similar_chunks(query)[:3]

    # 🔹 Step 2: Build clean context (IMPORTANT)
    context = "\n\n".join([r[1] for r in results])

    # 🔹 Step 3: Generate AI answer
    try:
        answer = generate_answer(query, context)
    except AIGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))

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
                "location": location,
            }
            for score, content, doc_name, youtube_url, source_type, source_url, location in results
        ],
    }
