"""
Merged summaries: one summary written from several documents together.

Citations work as for single documents (see summary_service): every stored
chunk gets a label [S0], [S1], ... (numbered across all sources), the model
only ever cites labels, and the code swaps each label for a citation built
from stored data. The citation also says which source it is, by the source's
number in the set:
    PDF "(1: p. 12)", PowerPoint "(2: Slide 4)", YouTube "[3: 02:05](link)",
    website "[4](link)", Word / PDF without pages "(5)".
A code-built "Sources" list at the top maps the numbers to document names.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.services.ai.flashcard_service import generate_cited_flashcards
from app.services.ai.summary_service import (
    CITATION_RULE,
    Citation,
    _final_summary,
    _summarize_labelled_batch,
    final_input_budget,
    fit_notes,
    plain_inline_math,
    replace_labels,
    run_calls,
)

# A source whose labelled text fits in one map batch is passed to the final
# step as is; longer ones are summarised batch by batch first (never mixing
# two sources in one batch, so each partial summary belongs to one source).
MAP_BATCH_CHARS = 3000
# Above this the material is too long for one call: map step first.
SINGLE_CALL_CHARS = 6000
FINAL_MAX_TOKENS = 1500

SOURCE_KINDS = {
    "pdf": "PDF",
    "pptx": "PowerPoint",
    "docx": "Word document",
    "youtube": "YouTube video",
    "website": "Web page",
    "image": "Images",
}

MERGED_SYSTEM_PROMPT = (
    "You are an expert study assistant creating one exam revision summary from several sources.\n"
    "Guidelines:\n"
    "1. Structure with clear Markdown headings and bullet points, organised by topic, not by source.\n"
    "2. When sources cover the same idea, combine them into one point and keep the labels of every source it came from.\n"
    "3. Prominently highlight key definitions and essential formulas/equations.\n"
    "4. Note where sources disagree, or where one explains something another leaves out. In your sentences, "
    "call sources 'Source 1', 'Source 2', ... (the numbers in the material's headings); never write the [S0], "
    "[S1], ... labels (or S0, S1, ...) as words in a sentence, they are only for citing.\n"
    "5. Keep the entire summary concise and strictly under 900 words.\n"
    "6. Output clean Markdown only. Write formulas in plain text or Unicode (e.g. x₁ + x₂, |V|, v = (x, y)), "
    "not LaTeX. Do not add a list of sources or a closing remark; the list is added automatically.\n"
    "7. " + CITATION_RULE + " Keep the labels from the material when you combine or rephrase points."
)


@dataclass
class MergedSource:
    """One document of a set, in set order (number = its position + 1)."""
    number: int
    title: str
    source_type: str
    source_url: Optional[str]
    chunks: List[str]
    # One per chunk, from build_chunk_citations; None where there's no location.
    citations: List[Citation] = field(default_factory=list)
    document_id: Optional[int] = None


def merged_citation(source: MergedSource, citation: Citation) -> Citation:
    """A chunk's citation with its source number in front."""
    n = str(source.number)
    if source.source_type == "website" and source.source_url:
        return (n, source.source_url)  # the page title is in the sources list
    if citation is None:
        return (n, None)
    label, url = citation
    return (f"{n}: {label}", url)


def join_by_source(labels: List[str]) -> str:
    """["1: p. 3", "1: pp. 5–6", "2: Slide 4", "3"] -> "1: p. 3, pp. 5–6; 2: Slide 4; 3"."""
    grouped = {}
    for label in labels:
        number, _, location = label.partition(": ")
        grouped.setdefault(number, [])
        if location:
            grouped[number].append(location)
    return "; ".join(f"{n}: {', '.join(locs)}" if locs else n for n, locs in grouped.items())


def _escape(text: str) -> str:
    return re.sub(r"([\[\]\\*_`])", r"\\\1", text)


def sources_list(sources: List[MergedSource]) -> str:
    """Markdown list mapping source numbers to documents (built by code, never by the model)."""
    lines = ["**Sources**", ""]
    for s in sources:
        title = _escape(s.title.strip() or (s.source_url or f"Source {s.number}"))
        if s.source_url and s.source_type in ("youtube", "website"):
            url = s.source_url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
            title = f"[{title}]({url})"
        lines.append(f"{s.number}. {title} — {SOURCE_KINDS.get(s.source_type, 'Document')}")
    return "\n".join(lines)


def generate_merged_summary(sources: List[MergedSource]) -> str:
    """Summary of all `sources` together, each point citing its source(s) and location.

    Raises AIGenerationError (from the AI calls) with a plain message.
    """
    labelled: List[List[str]] = []   # per source: its labelled chunk blocks
    citations: List[Citation] = []   # per global label
    for s in sources:
        blocks = []
        for i, text in enumerate(s.chunks):
            text = (text or "").strip()
            if not text:
                continue
            blocks.append(f"[S{len(citations)}] {text}")
            citations.append(merged_citation(s, s.citations[i] if i < len(s.citations) else None))
        labelled.append(blocks)
    if not citations:
        return "No text content available to summarize."

    def heading(s: MergedSource) -> str:
        return f"## Source {s.number}: {s.title} ({SOURCE_KINDS.get(s.source_type, 'Document')})"

    total = sum(len(b) + 2 for blocks in labelled for b in blocks)
    # Per source: its text as is, or the map batches to summarise (a batch never
    # mixes two sources). All sources' batches share one pool of parallel calls.
    plans = []
    for s, blocks in zip(sources, labelled):
        if not blocks:
            continue
        text = "\n\n".join(blocks)
        if total > SINGLE_CALL_CHARS and len(text) > MAP_BATCH_CHARS:
            batches, current, current_len = [], [], 0
            for block in blocks:
                if current and current_len + len(block) > MAP_BATCH_CHARS:
                    batches.append(current)
                    current, current_len = [], 0
                current.append(block)
                current_len += len(block) + 2
            if current:
                batches.append(current)
            plans.append((s, None, batches))
        else:
            plans.append((s, text, []))
    all_batches = [batch for _, _, batches in plans for batch in batches]
    notes = iter(run_calls(lambda batch: _summarize_labelled_batch("\n".join(batch)), all_batches))
    parts = []
    for s, text, batches in plans:
        if text is None:
            text = "\n\n".join(next(notes) for _ in batches)
        parts.append(f"{heading(s)}\n{text}")

    # Many or long sources: combine the notes in rounds until the final call can take them.
    parts = fit_notes(parts, final_input_budget(FINAL_MAX_TOKENS), cite=True)
    summary = _final_summary("\n\n".join(parts), MERGED_SYSTEM_PROMPT, max_tokens=FINAL_MAX_TOKENS)
    body = plain_inline_math(replace_labels(summary, citations, join_plain=join_by_source))
    return f"{sources_list(sources)}\n\n---\n\n{body}"


# ─── Merged flashcards ───


def allocate_cards(count: int, sizes: List[int]) -> List[int]:
    """Split `count` cards over sources by text size, at least 1 each.

    Largest-remainder rounding, so the shares add up to `count` exactly.
    Sources with no text get 0. With fewer cards than sources, the largest
    sources get one each.
    """
    live = [i for i, size in enumerate(sizes) if size > 0]
    shares = [0] * len(sizes)
    if not live or count <= 0:
        return shares
    if count <= len(live):
        for i in sorted(live, key=lambda i: -sizes[i])[:count]:
            shares[i] = 1
        return shares
    for i in live:
        shares[i] = 1
    spare = count - len(live)
    total = sum(sizes[i] for i in live)
    exact = {i: spare * sizes[i] / total for i in live}
    for i in live:
        shares[i] += int(exact[i])
    leftover = count - sum(shares)
    for i in sorted(live, key=lambda i: (-(exact[i] - int(exact[i])), -sizes[i]))[:leftover]:
        shares[i] += 1
    return shares


def merged_card_citation(source: MergedSource, label: Optional[str], url: Optional[str]):
    """(label, url) for a merged card: always names the source, then the location if known.

    "Graph_PPT.pdf · p. 12", "YouTube: abc · 02:05" (+ timestamp link), a web
    page's title (+ its link), or just the name (Word, or no usable citation).
    """
    title = source.title.strip() or f"Source {source.number}"
    if source.source_type == "website":
        return title, source.source_url
    if label:
        return f"{title} · {label}", url
    return title, None


def generate_merged_flashcards(sources: List[MergedSource], count: int = 10) -> List[dict]:
    """A deck covering every source, grouped by source in set order.

    Each source's share (allocate_cards) comes from generate_cited_flashcards,
    which spreads it across that source. Cards carry "document_id".
    Raises AIGenerationError if any source's generation fails.
    """
    sizes = [sum(len((c or "").strip()) for c in s.chunks) for s in sources]
    deck = []
    for source, share in zip(sources, allocate_cards(count, sizes)):
        if share == 0:
            continue
        for card in generate_cited_flashcards(source.chunks, source.citations, count=share):
            label, url = merged_card_citation(source, card.get("source_label"), card.get("source_url"))
            deck.append({
                "question": card["question"],
                "answer": card["answer"],
                "source_label": label,
                "source_url": url,
                "document_id": source.document_id,
            })
    return deck
