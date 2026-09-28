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

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)


def search_similar_chunks(query: str, top_k: int = 5):
    """Returns a list of (score, content, document_name, youtube_timestamp_url) tuples,
    most similar first.
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
        youtube_timestamp_url = None

        if source_type == "youtube":
            source_url = meta.get("source_url", "")
            start_seconds = meta.get("start_seconds")
            if source_url:
                if start_seconds is not None and start_seconds >= 0:
                    sep = "&" if "?" in source_url else "?"
                    if "youtu.be" in source_url:
                        youtube_timestamp_url = f"{source_url}{sep}t={start_seconds}"
                    else:
                        youtube_timestamp_url = f"{source_url}{sep}t={start_seconds}s"
                else:
                    youtube_timestamp_url = source_url

        scored_results.append((float(similarity), content, doc_name, youtube_timestamp_url))

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
