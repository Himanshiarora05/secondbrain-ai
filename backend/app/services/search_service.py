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

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)


def search_similar_chunks(query: str, top_k: int = 5):
    """Returns a list of (score, content, document_name, youtube_timestamp_url,
    source_type, source_url) tuples, most similar first.
    """
    collection = get_collection()
    query_embedding = get_embedding(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
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

        if source_type == "youtube":
            youtube_timestamp_url = YouTubeService.generate_timestamp_url(
                source_url or "", meta.get("start_seconds")
            )

        scored_results.append(
            (float(similarity), content, doc_name, youtube_timestamp_url, source_type, source_url)
        )

    return scored_results


def generate_answer(query: str, context: str) -> str:
    try:
        response = client.chat.completions.create(
            model="openai/gpt-3.5-turbo",
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
        return response.choices[0].message.content

    except Exception as e:
        return f"ERROR: {str(e)}"
