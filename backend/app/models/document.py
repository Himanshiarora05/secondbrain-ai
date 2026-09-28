from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship
from app.database.db import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(String, unique=True, index=True)
    filename = Column(String, nullable=False)
    content = Column(Text)
    source_type = Column(String, default="pdf", nullable=False)
    source_url = Column(String, nullable=True)
    metadata_json = Column(Text, nullable=True)

    chunks = relationship(
        "Chunk", back_populates="document", cascade="all, delete-orphan"
    )
    summary = relationship(
        "Summary", back_populates="document", uselist=False, cascade="all, delete-orphan"
    )
    flashcards = relationship(
        "Flashcard", back_populates="document", cascade="all, delete-orphan"
    )
