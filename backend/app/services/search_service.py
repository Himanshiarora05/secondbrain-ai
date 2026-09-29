"""
Search (retrieval + generation).

Previously search_similar_chunks() pulled every single Chunk row out of
Postgres on every request, json.loads()'d its stored embedding, and
computed cosine similarity by hand in a Python loop. That doesn't scale
past a small library and re-loaded a second copy of the embedding model
on top of the one in rag_service.py. This version queries Chroma's index
(see app/database/chroma.py) directly and shares the single embedding
model from app/services/embedding_service.py.
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

from app.database.chroma import get_collection
from app.services.embedding_service import get_embedding
from app.services.youtube.youtube_service import YouTubeService
from app.services.ai.summary_service import (
    MODEL_NAME, AIGenerationError, ai_failure, format_pages, format_timestamp, reply_text,
)

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)


def search_similar_chunks(query: str, user_id: int, top_k: int = 5):
    """The user's chunks most similar to `query`, as a list of (score, content,
    document_name, youtube_timestamp_url, source_type, source_url, location)
    tuples, most similar first. Only chunks whose metadata has this user_id are
    searched (set at upload, or by scripts/assign_documents_to_user.py).

    location is a short citation for the match: "02:05" for YouTube, "p. 12"
    / "pp. 12–13" for PDFs with page ranges, otherwise None.
    """
    collection = get_collection()
    query_embedding = get_embedding(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"user_id": user_id},
    )

    if not results["ids"] or not results["ids"][0]:
        return []

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]  # cosine distance: lower = more similar

    scored_results = []
    for content, meta, distance in zip(documents, metadatas, distances):
        similarity = 1 - distance  # convert distance back to a similarity score
        doc_name = meta.get("filename", "Unknown")
        source_type = meta.get("source_type", "pdf")
        source_url = meta.get("source_url") or None
        youtube_timestamp_url = None
        location = None

        if source_type == "youtube":
            youtube_timestamp_url = YouTubeService.generate_timestamp_url(
                source_url or "", meta.get("start_seconds")
            )
            if meta.get("start_seconds") is not None:
                location = format_timestamp(meta["start_seconds"])
        elif source_type == "pdf":
            location = format_pages(meta.get("page_start"), meta.get("page_end"))

        scored_results.append(
            (float(similarity), content, doc_name, youtube_timestamp_url, source_type, source_url, location)
        )

    return scored_results


def generate_answer(query: str, context: str) -> str:
    """AI answer for the query from the retrieved context.

    Raises AIGenerationError with a plain message (used to return "ERROR: ..."
    as if it were the answer).
    """
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "You are a smart tutor. Explain clearly in simple words with examples.",
                },
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {query}",
                },
            ],
            temperature=0.5,
        )
        return reply_text(response, "answering a search")

    except AIGenerationError:
        raise
    except Exception as e:
        raise ai_failure(e, "answering a search") from e
