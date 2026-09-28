"""
Chunking for RAG ingestion.

The old version of chunk_text() did `text[i:i+500]` - a blind character
slice with no overlap and no regard for sentence or paragraph boundaries.
For study notes that means a definition, formula, or bullet point gets
sliced in half roughly as often as not, which hurts both search relevance
and the quality of whatever gets summarized from a chunk later.

This version splits on sentence boundaries first, then greedily packs
sentences into ~chunk_size-character chunks, carrying a bit of overlap
between consecutive chunks so a concept that starts near a chunk boundary
still has context on both sides.
"""

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])|\n{2,}")


def _split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    pieces = _SENTENCE_SPLIT.split(text)
    return [p.strip() for p in pieces if p.strip()]


class RAGService:

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
        """Pack sentences into chunks of roughly `chunk_size` characters,
        with `overlap` characters carried over from the tail of one chunk
        into the start of the next so context isn't lost at the seam.
        """
        sentences = _split_sentences(text)
        if not sentences:
            return []

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for sentence in sentences:
            # A single sentence longer than chunk_size: flush what we have,
            # then hard-slice the giant sentence on its own (rare, but
            # avoids one enormous "sentence" blowing past chunk_size).
            if len(sentence) > chunk_size:
                if current:
                    chunks.append(" ".join(current))
                    current, current_len = [], 0
                for i in range(0, len(sentence), chunk_size):
                    chunks.append(sentence[i:i + chunk_size])
                continue

            if current_len + len(sentence) + 1 > chunk_size and current:
                chunks.append(" ".join(current))

                # Carry overlap: keep trailing sentences whose combined
                # length is <= `overlap` as the start of the next chunk.
                carried: list[str] = []
                carried_len = 0
                for s in reversed(current):
                    if carried_len + len(s) > overlap:
                        break
                    carried.insert(0, s)
                    carried_len += len(s) + 1
                current, current_len = carried, carried_len

            current.append(sentence)
            current_len += len(sentence) + 1

        if current:
            chunks.append(" ".join(current))

        return chunks
