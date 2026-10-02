"""
Rebuild the Chroma collection from the chunks in Postgres.

Postgres is the source of truth: every chunk's text is in `chunks`, and the
document it belongs to says who owns it and what kind of source it is. Chroma
only holds vectors, which can be recomputed. On a host without a persistent
disk (Hugging Face Spaces' free tier) the vector store starts empty after
every restart, so `rebuild_if_empty` runs at startup and puts back every
vector with the same id and metadata an upload would have given it (see
`_store_document_and_chunks` in app/api/upload.py).
"""

BATCH_SIZE = 256


def chunk_metadata(doc, chunk, chunk_index: int) -> dict:
    """The Chroma metadata an upload stores for this chunk."""
    meta = {
        "document_id": doc.id,
        "filename": doc.filename,
        "chunk_index": chunk_index,
        "source_type": doc.source_type,
    }
    # Search only returns the signed-in user's chunks (search_service filters on it).
    if doc.user_id is not None:
        meta["user_id"] = doc.user_id
    if doc.source_url:
        meta["source_url"] = doc.source_url
    if chunk.start_seconds is not None:
        meta["start_seconds"] = chunk.start_seconds
    if chunk.page_start is not None:
        meta["page_start"] = chunk.page_start
        meta["page_end"] = chunk.page_end if chunk.page_end is not None else chunk.page_start
    return meta


def _rows(db):
    """Every (document, chunk, index within its document), in upload order."""
    from app.models.chunk import Chunk
    from app.models.document import Document

    query = (
        db.query(Document, Chunk)
        .join(Chunk, Chunk.document_id == Document.id)
        .order_by(Document.id, Chunk.id)
        .yield_per(BATCH_SIZE)
    )
    current_doc, index = None, 0
    for doc, chunk in query:
        if doc.id != current_doc:
            current_doc, index = doc.id, 0
        yield doc, chunk, index
        index += 1


def rebuild_collection(db, collection, embed) -> int:
    """Embed every chunk in Postgres and upsert it into `collection`. Returns the count."""
    total = 0
    ids, texts, metadatas = [], [], []

    def flush():
        nonlocal total
        if not ids:
            return
        collection.upsert(ids=ids, embeddings=embed(texts), documents=texts, metadatas=metadatas)
        total += len(ids)
        ids.clear(), texts.clear(), metadatas.clear()

    for doc, chunk, index in _rows(db):
        # Chunks always get "{document_id}-{index}" at upload; the fallback is for rows
        # without one (deleting a document also removes its vectors by document_id).
        ids.append(chunk.chroma_id or f"{doc.id}-{index}")
        texts.append(chunk.content or "")
        metadatas.append(chunk_metadata(doc, chunk, index))
        if len(ids) >= BATCH_SIZE:
            flush()
    flush()
    return total


def rebuild_if_empty(db=None, collection=None, embed=None) -> int:
    """Rebuild the vector store when it has nothing in it. Returns the number of chunks added."""
    if collection is None:
        from app.database.chroma import get_collection
        collection = get_collection()
    if collection.count() > 0:
        return 0
    if embed is None:
        from app.services.embedding_service import get_embeddings
        embed = get_embeddings

    own_session = db is None
    if own_session:
        from app.database.db import SessionLocal
        db = SessionLocal()
    try:
        return rebuild_collection(db, collection, embed)
    finally:
        if own_session:
            db.close()
