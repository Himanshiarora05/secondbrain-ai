from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Integer, Text, ForeignKey, String
from sqlalchemy.orm import relationship
from app.database.db import Base
from app.services.embedding_service import EMBEDDING_DIM


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    content = Column(Text)

    # Legacy: the chunk's id in the Chroma vector store this app used before
    # pgvector ("{document_id}-{chunk_index}"). New chunks leave it null; it is
    # only read by scripts/migrate_chroma_to_pgvector.py to match old vectors.
    chroma_id = Column(String, unique=True, index=True)
    start_seconds = Column(Integer, nullable=True)
    # PDF only: physical pages the chunk's text came from (equal for a one-page
    # chunk). Null for other sources and for PDFs uploaded before page tracking.
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)

    document = relationship("Document", back_populates="chunks")
    # The chunk's search vector. The database deletes it with the chunk
    # (ON DELETE CASCADE), so deleting chunks never has to load vectors.
    embedding = relationship(
        "ChunkEmbedding", uselist=False, cascade="all, delete-orphan", passive_deletes=True,
    )


class ChunkEmbedding(Base):
    """One chunk's search vector (pgvector). Search joins it to `chunks` and
    `documents`, so the owner (user_id), document, name, source type, pages and
    timestamps all come from those rows - there is no second copy to keep in sync."""
    __tablename__ = "chunk_embeddings"

    chunk_id = Column(Integer, ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)
