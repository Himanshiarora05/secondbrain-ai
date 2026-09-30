"""
AI-powered Flashcard Generation Service.

Generates strict JSON flashcard decks for exam revision.
Includes defensive JSON parsing and map-reduce chunking for long documents.
"""

import json
import math
import re
import os
from typing import List, Dict, Optional, Tuple
import openai
from dotenv import load_dotenv
from openai import OpenAI

from app.services.ai.model_limits import cap_tokens
from app.services.rag.rag_service import RAGService
from app.services.ai.summary_service import (
    MODEL_NAME, REASONING_ALLOWANCE, AIGenerationError, ai_failure, check_reply, format_pages, format_timestamp,
    is_daily_limit,
)
from app.services.youtube.youtube_service import YouTubeService

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    timeout=30,
)

MAP_REDUCE_THRESHOLD = 6000


def _parse_flashcard_json(raw_text: str) -> List[Dict[str, str]]:
    """Defensively parse JSON from LLM response, stripping code blocks and markdown."""
    text = raw_text.strip()

    # Remove markdown code blocks if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    # Find the JSON array substring if surrounded by commentary
    match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if match:
        text = match.group(0)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: attempt basic regex extraction of question-answer pairs
        qa_pairs = []
        pattern = re.compile(r'"question"\s*:\s*"([^"]+)"\s*,\s*"answer"\s*:\s*"([^"]+)"', re.DOTALL)
        for q_match in pattern.finditer(text):
            qa_pairs.append({
                "question": q_match.group(1).strip(),
                "answer": q_match.group(2).strip(),
            })
        if qa_pairs:
            return qa_pairs
        raise ValueError(f"Failed to parse LLM flashcards as JSON: {raw_text[:200]}")

    if not isinstance(data, list):
        raise ValueError("Flashcard response is not a list")

    validated: List[Dict[str, str]] = []
    for item in data:
        if isinstance(item, dict) and "question" in item and "answer" in item:
            q = str(item["question"]).strip()
            a = str(item["answer"]).strip()
            if q and a:
                card = {"question": q, "answer": a}
                if item.get("source") is not None:
                    card["source"] = item["source"]
                validated.append(card)

    return validated


SOURCE_RULE = (
    "- The material is split into sections labelled [S0], [S1], [S2], ... "
    "Give each card a 'source' key with the ONE label of the section it came from, exactly as written, "
    "e.g. \"source\": \"S3\". Never write times, page numbers or URLs yourself.\n"
    "- Spread the cards across ALL the sections, from the first to the last, instead of "
    "taking them all from the beginning.\n"
)


def _generate_flashcards_from_text(text_segment: str, count: int, cite: bool = False) -> List[Dict[str, str]]:
    """Single-pass call to generate flashcards from text.

    With cite=True the text carries [S<i>] labels and each card should come
    back with a 'source' label (validated by the caller).
    """
    json_shape = '[{"question": "...", "answer": "...", "source": "S0"}]' if cite else '[{"question": "...", "answer": "..."}]'
    system_prompt = (
        "You are an expert exam tutor creating flashcards for spaced repetition study.\n"
        "Return STRICT JSON only — an array of objects, each with 'question' and 'answer' keys.\n"
        "Rules:\n"
        "- Focus on high-yield exam facts, core definitions, formulas, and key concepts.\n"
        "- Keep questions direct and specific.\n"
        "- Keep answers clear, accurate, and concise (1-3 sentences).\n"
        + (SOURCE_RULE if cite else "")
        + f"- Do NOT include any intro, outro, or markdown code blocks. Output ONLY raw JSON: {json_shape}"
    )

    user_prompt = f"""Generate {count} exam flashcards based on the following material:

{text_segment}

STRICT JSON FLASHCARDS:"""

    last_exception = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4 if attempt == 0 else 0.2,
                max_tokens=cap_tokens(1200 + REASONING_ALLOWANCE),
            )
            check_reply(response, "generating flashcards")
            content = response.choices[0].message.content or ""
            cards = _parse_flashcard_json(content)
            if cards:
                return cards
            last_exception = ValueError("LLM returned empty or unparseable flashcards")
        except openai.APIStatusError as e:
            if e.status_code in (401, 402, 403) or is_daily_limit(e):  # key, credit or daily-limit problem: a retry can't help
                raise ai_failure(e, "generating flashcards") from e
            last_exception = e
        except Exception as e:
            last_exception = e

    if isinstance(last_exception, ValueError):  # the model answered, but not with usable cards
        raise AIGenerationError("The AI returned flashcards in an unexpected format. Please try again.")
    raise ai_failure(last_exception, "generating flashcards") from last_exception


def generate_flashcards(document_text: str, count: int = 10) -> List[Dict[str, str]]:
    """Generate high-yield flashcards from document text.

    If document_text exceeds MAP_REDUCE_THRESHOLD (~6000 chars), splits the text
    using RAGService.chunk_text, generates flashcards from multiple sections,
    and deduplicates to return up to `count` flashcards.
    """
    if not document_text or not document_text.strip():
        return []

    cleaned_text = document_text.strip()

    if len(cleaned_text) > MAP_REDUCE_THRESHOLD:
        chunks = RAGService.chunk_text(cleaned_text, chunk_size=3000, overlap=300)
        if len(chunks) > 1:
            per_chunk_count = max(3, (count // len(chunks)) + 2)
            all_cards: List[Dict[str, str]] = []
            seen_questions = set()

            for chunk in chunks:
                chunk_cards = _generate_flashcards_from_text(chunk, count=per_chunk_count)
                for card in chunk_cards:
                    norm_q = card["question"].lower().strip(" ?.")
                    if norm_q not in seen_questions:
                        seen_questions.add(norm_q)
                        all_cards.append(card)
                        if len(all_cards) >= count:
                            break
                if len(all_cards) >= count:
                    break

            return all_cards[:count]

    # For shorter documents, generate directly
    cards = _generate_flashcards_from_text(cleaned_text, count=count)
    return cards[:count]


# ─── Flashcards with source citations ───
#
# Same rule as YouTube summaries: the model only ever picks a chunk label
# ([S3]); the citation (timestamp link, page link, slide number) is built
# here from stored chunk data. A label that isn't in the batch the model was
# shown is dropped, and the card is kept without a citation.

Citation = Optional[Tuple[str, Optional[str]]]  # (label, url or None)

BATCH_CHARS = 3000
CARDS_PER_CALL = 3  # roughly how many cards to ask each batch for when sampling a long source
_SLIDE_MARKER_RE = re.compile(r"\[Slide (\d+)")
_SOURCE_INDEX_RE = re.compile(r"(\d+)")


def _slide_label(slides: List[int]) -> Optional[str]:
    if not slides:
        return None
    lo, hi = min(slides), max(slides)
    return f"Slide {lo}" if lo == hi else f"Slides {lo}–{hi}"


def build_chunk_citations(
    source_type: str,
    source_url: Optional[str],
    title: str,
    chunks: List[Tuple[str, Optional[int]]],
    pages: Optional[List[Tuple[Optional[int], Optional[int]]]] = None,
) -> List[Citation]:
    """One citation per chunk, from stored data only.

    `chunks` is [(text, start_seconds), ...] in document order; `pages` is
    [(page_start, page_end), ...] for the same chunks (PDFs).
    - youtube: ("02:05", link to that moment)
    - website: (page title, page URL)
    - pptx:    ("Slide 4" / "Slides 3–4", None), tracking the current slide
               across chunks so a chunk that starts mid-slide is still numbered
    - pdf:     ("p. 12" / "pp. 12–13", None) from the stored page range;
               None for PDFs uploaded before pages were recorded
    - docx and anything else: None (no location is stored)
    """
    if source_type == "youtube" and source_url:
        return [
            (format_timestamp(start), YouTubeService.generate_timestamp_url(source_url, start))
            if start is not None else None
            for _, start in chunks
        ]

    if source_type == "pdf" and pages:
        labels = [format_pages(start, end) for start, end in pages]
        return [(label, None) if label else None for label in labels]

    if source_type == "website" and source_url:
        return [(title or source_url, source_url) for _ in chunks]

    if source_type == "pptx":
        citations: List[Citation] = []
        current: Optional[int] = None
        for text, _ in chunks:
            markers = [(m.start(), int(m.group(1))) for m in _SLIDE_MARKER_RE.finditer(text)]
            slides = []
            # Text before the first marker belongs to the slide carried over from earlier chunks.
            first_pos = markers[0][0] if markers else len(text)
            if current is not None and text[:first_pos].strip():
                slides.append(current)
            slides.extend(n for _, n in markers)
            label = _slide_label(slides)
            citations.append((label, None) if label else None)
            if markers:
                current = markers[-1][1]
        return citations

    return [None for _ in chunks]


def _batch_indices(texts: List[str]) -> List[List[int]]:
    """Group consecutive chunk indices into batches of about BATCH_CHARS (never splitting a chunk)."""
    batches, current, current_len = [], [], 0
    for i, text in enumerate(texts):
        block_len = len(text) + 8  # label + separator
        if current and current_len + block_len > BATCH_CHARS:
            batches.append(current)
            current, current_len = [], 0
        current.append(i)
        current_len += block_len
    if current:
        batches.append(current)
    return batches


def _pick_spread(n: int, k: int) -> List[int]:
    """k indices spread evenly over range(n), always including the first and last."""
    if k >= n:
        return list(range(n))
    if k == 1:
        return [0]
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


def _resolve_source(raw, allowed: set) -> Optional[int]:
    """Turn the model's 'source' value ("S3", "[S3]", 3, ["S3"]) into a chunk index it was shown."""
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None:
        return None
    match = _SOURCE_INDEX_RE.search(str(raw))
    if not match:
        return None
    idx = int(match.group(1))
    return idx if idx in allowed else None


def generate_cited_flashcards(chunks: List[str], citations: List[Citation], count: int = 10) -> List[Dict]:
    """Flashcards spread across the whole source, each citing the chunk it came from.

    `chunks` are the stored chunk texts in document order, and `citations[i]`
    is the citation for chunks[i]. Returns
    [{"question", "answer", "source_label", "source_url"}, ...].
    """
    texts = [c.strip() for c in chunks]
    if not any(texts):
        return []

    # The model tends to write all its cards from the start of what it's shown,
    # so coverage is enforced here: each call sees one slice of the source.
    wanted = max(1, math.ceil(count / CARDS_PER_CALL))
    total_len = sum(len(t) + 8 for t in texts)
    if total_len <= MAP_REDUCE_THRESHOLD:
        # Short source: split all of it into `wanted` consecutive groups.
        n = len(texts)
        groups = min(wanted, n)
        bounds = [round(g * n / groups) for g in range(groups + 1)]
        batches = [list(range(bounds[g], bounds[g + 1])) for g in range(groups)]
    else:
        # Long source: sample ~BATCH_CHARS batches evenly from start to end.
        all_batches = _batch_indices(texts)
        batches = [all_batches[i] for i in _pick_spread(len(all_batches), wanted)]

    per_batch = count if len(batches) == 1 else math.ceil(count / len(batches)) + 1

    per_batch_cards: List[List[Dict]] = []
    for batch in batches:
        labelled = "\n\n".join(f"[S{i}] {texts[i]}" for i in batch if texts[i])
        raw_cards = _generate_flashcards_from_text(labelled, count=per_batch, cite=True)
        allowed = set(batch)
        cards = []
        for card in raw_cards:
            idx = _resolve_source(card.get("source"), allowed)
            citation = citations[idx] if idx is not None and idx < len(citations) else None
            cards.append({
                "question": card["question"],
                "answer": card["answer"],
                "source_label": citation[0] if citation else None,
                "source_url": citation[1] if citation else None,
            })
        per_batch_cards.append(cards)

    # Pick round-robin across batches so the deck covers the whole source, not
    # just its start, then return the picks in source order for studying.
    picked: List[Tuple[int, int]] = []
    seen_questions = set()
    for rank in range(max((len(c) for c in per_batch_cards), default=0)):
        for b, cards in enumerate(per_batch_cards):
            if rank >= len(cards) or len(picked) >= count:
                continue
            norm_q = cards[rank]["question"].lower().strip(" ?.")
            if norm_q not in seen_questions:
                seen_questions.add(norm_q)
                picked.append((b, rank))
    return [per_batch_cards[b][rank] for b, rank in sorted(picked)]
