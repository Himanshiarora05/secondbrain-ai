from sqlalchemy import Column, Integer, Text, ForeignKey, String
from sqlalchemy.orm import relationship
from app.database.db import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    content = Column(Text)

    # ID of the matching vector in the Chroma collection (see
    # app/database/chroma.py). The embedding itself is NOT stored here
    # anymore - previously it was serialized as a JSON string in Postgres
    # and search.py had to load every row and do cosine similarity in
    # Python, which doesn't scale. Chroma now owns the vector index.
    chroma_id = Column(String, unique=True, index=True)
    start_seconds = Column(Integer, nullable=True)

    document = relationship("Document", back_populates="chunks")
