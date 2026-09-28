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
from typing import TypeVar

T = TypeVar("T")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])|\n{2,}")


def _split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    pieces = _SENTENCE_SPLIT.split(text)
    return [p.strip() for p in pieces if p.strip()]


def _pack(items: list[tuple[str, T]], chunk_size: int, overlap: int) -> list[tuple[str, list[T]]]:
    """Pack (sentence, tag) pairs into ~chunk_size-character chunks.

    Returns (chunk_text, tags of the sentences in it). The tag rides along
    with each sentence (a PDF page number, or None) so a chunk knows where
    its text came from, including sentences carried over as overlap.
    """
    chunks: list[list[tuple[str, T]]] = []
    current: list[tuple[str, T]] = []
    current_len = 0

    for sentence, tag in items:
        # A single sentence longer than chunk_size: flush what we have,
        # then hard-slice the giant sentence on its own (rare, but
        # avoids one enormous "sentence" blowing past chunk_size).
        if len(sentence) > chunk_size:
            if current:
                chunks.append(current)
                current, current_len = [], 0
            for i in range(0, len(sentence), chunk_size):
                chunks.append([(sentence[i:i + chunk_size], tag)])
            continue

        if current_len + len(sentence) + 1 > chunk_size and current:
            chunks.append(current)

            # Carry overlap: keep trailing sentences whose combined
            # length is <= `overlap` as the start of the next chunk.
            carried: list[tuple[str, T]] = []
            carried_len = 0
            for s, t in reversed(current):
                if carried_len + len(s) > overlap:
                    break
                carried.insert(0, (s, t))
                carried_len += len(s) + 1
            current, current_len = carried, carried_len

        current.append((sentence, tag))
        current_len += len(sentence) + 1

    if current:
        chunks.append(current)

    return [(" ".join(s for s, _ in chunk), [t for _, t in chunk]) for chunk in chunks]


class RAGService:

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
        """Pack sentences into chunks of roughly `chunk_size` characters,
        with `overlap` characters carried over from the tail of one chunk
        into the start of the next so context isn't lost at the seam.
        """
        items = [(s, None) for s in _split_sentences(text)]
        return [chunk for chunk, _ in _pack(items, chunk_size, overlap)]

    @staticmethod
    def chunk_pages(pages: list[str], chunk_size: int = 800, overlap: int = 150) -> list[dict]:
        """Like chunk_text, for a PDF's pages: each chunk also gets the pages it covers.

        `pages` is the text of each page in order (page 1 first). Returns
        [{"text", "page_start", "page_end"}, ...] with 1-based physical page
        numbers. A chunk that runs across a page break (or carries overlap
        from the previous page) spans two pages: page_start < page_end.
        Sentences are split per page, so none runs across a page break.
        """
        items = [(s, page_no) for page_no, text in enumerate(pages, start=1) for s in _split_sentences(text)]
        return [
            {"text": chunk, "page_start": min(page_nos), "page_end": max(page_nos)}
            for chunk, page_nos in _pack(items, chunk_size, overlap)
        ]
