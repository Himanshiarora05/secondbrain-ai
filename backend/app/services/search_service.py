"""
Search (retrieval + generation).

Retrieval is one query in Postgres: pgvector's cosine distance between the
query's embedding and every chunk_embeddings row of the user's documents
(joined through chunks and documents, so ownership, names, pages and
timestamps come straight from those rows), nearest first. The embedding model
is shared via app/services/embedding_service.py.

The scan is exact (no approximate index): it reads one user's vectors, which
stays quick at the size of a personal library and never misses a match the
way a filtered approximate search can.
"""

import os
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy.orm import Session

from app.models.chunk import Chunk, ChunkEmbedding
from app.models.document import Document
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


def nearest_chunks(db: Session, query_embedding: list[float], user_id: int, top_k: int = 5):
    """(chunk, document, cosine distance) for the user's chunks nearest to the
    embedding, nearest first."""
    distance = ChunkEmbedding.embedding.cosine_distance(query_embedding).label("distance")
    return (
        db.query(Chunk, Document, distance)
        .join(ChunkEmbedding, ChunkEmbedding.chunk_id == Chunk.id)
        .join(Document, Document.id == Chunk.document_id)
        .filter(Document.user_id == user_id)
        .order_by(distance, Chunk.id)
        .limit(top_k)
        .all()
    )


def search_similar_chunks(db: Session, query: str, user_id: int, top_k: int = 5):
    """The user's chunks most similar to `query`, as a list of (score, content,
    document_name, youtube_timestamp_url, source_type, source_url, location)
    tuples, most similar first. Only chunks of documents owned by user_id are
    searched.

    location is a short citation for the match: "02:05" for YouTube, "p. 12"
    / "pp. 12–13" for PDFs with page ranges and image uploads, otherwise None.
    """
    scored_results = []
    for chunk, doc, distance in nearest_chunks(db, get_embedding(query), user_id, top_k):
        similarity = 1 - distance  # cosine distance: lower = more similar
        source_type = doc.source_type or "pdf"
        source_url = doc.source_url or None
        youtube_timestamp_url = None
        location = None

        if source_type == "youtube":
            youtube_timestamp_url = YouTubeService.generate_timestamp_url(source_url or "", chunk.start_seconds)
            if chunk.start_seconds is not None:
                location = format_timestamp(chunk.start_seconds)
        elif source_type in ("pdf", "image"):
            location = format_pages(chunk.page_start, chunk.page_end)

        scored_results.append(
            (float(similarity), chunk.content, doc.filename or "Unknown", youtube_timestamp_url,
             source_type, source_url, location)
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
