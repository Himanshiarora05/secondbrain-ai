"""
AI-powered Document Summarization Service.

Generates structured, exam-revision summaries using OpenRouter.
For documents longer than ~6000 characters, uses a chunk-and-map-reduce approach
to avoid context overflow and provide a coherent, high-yield summary.
"""

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple
import httpx
import openai
from dotenv import load_dotenv
from openai import OpenAI

from app.services.ai.model_limits import cap_tokens, context_tokens
from app.services.rag.rag_service import RAGService
from app.services.youtube.youtube_service import YouTubeService

load_dotenv()

logger = logging.getLogger(__name__)


class AIGenerationError(Exception):
    """Raised when AI generation fails via OpenAI / OpenRouter.

    str() is a plain message that is safe to show to the user; the raw error
    is chained as __cause__ and logged where it is raised.
    """
    pass


_AI_STATUS_MESSAGES = {
    401: "The AI service rejected the API key. Check OPENROUTER_API_KEY in backend/.env.",
    402: "The AI service is out of credits. Add credits at openrouter.ai to generate summaries, flashcards and answers.",
    403: "The AI service refused this request. The API key may not have access to this model.",
    # OpenRouter's answer for an unknown model id, and for a free model when the
    # account's privacy settings exclude every provider that serves it.
    404: "The AI model isn't available. Check OPENROUTER_MODEL in backend/.env and your OpenRouter privacy settings.",
    429: "The AI service is busy right now (rate limit reached). Please wait a minute and try again.",
}


def is_daily_limit(exc: BaseException) -> bool:
    """OpenRouter's daily cap on free-model requests (50 a day on an account
    without credits). It only resets the next day, so retrying can't help."""
    return (
        isinstance(exc, openai.APIStatusError)
        and exc.status_code == 429
        and ("free-models-per-day" in str(exc) or "openrouter_free_tier_daily" in str(exc))
    )


DAILY_LIMIT_MESSAGE = (
    "Today's free AI requests are used up (free models allow 50 a day on an account without credits). "
    "They reset at midnight UTC, or add credits at openrouter.ai to raise the limit."
)


def ai_error_message(exc: BaseException) -> str:
    """Turn an OpenAI/OpenRouter failure into a plain message for the user."""
    if is_daily_limit(exc):
        return DAILY_LIMIT_MESSAGE
    if isinstance(exc, openai.APITimeoutError):
        return "The AI service took too long to respond. Please try again."
    if isinstance(exc, openai.APIConnectionError):
        return "Could not reach the AI service. Check your internet connection and try again."
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code in _AI_STATUS_MESSAGES:
            return _AI_STATUS_MESSAGES[exc.status_code]
        if exc.status_code >= 500:
            return "The AI service is having problems right now. Please try again in a few minutes."
    return "The AI service couldn't complete this request. Please try again."


def ai_failure(exc: BaseException, what: str) -> AIGenerationError:
    """Log the raw error and return an AIGenerationError with the plain message."""
    logger.warning(f"AI call failed while {what}: {exc}")
    return AIGenerationError(ai_error_message(exc))


client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    timeout=30,
)

# gpt-4o-mini: cheaper than gpt-3.5-turbo ($0.15 / $0.60 per million tokens vs $0.50 / $1.50),
# a 128k-token context (vs 16k) and up to 16k output tokens (vs 4k).
DEFAULT_MODEL = "openai/gpt-4o-mini"


def configured_model() -> str:
    """The OpenRouter model for summaries, flashcards and search answers.

    OPENROUTER_MODEL in backend/.env overrides the default (e.g. a ":free" model
    for testing); remove it to go back. Read once at import, so a change needs
    a backend restart (--reload doesn't watch .env).
    """
    return os.getenv("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL


MODEL_NAME = configured_model()
if MODEL_NAME != DEFAULT_MODEL:
    logger.warning(f"Using OpenRouter model {MODEL_NAME} (OPENROUTER_MODEL), not the default {DEFAULT_MODEL}")

MAP_REDUCE_THRESHOLD = 6000

# Reasoning models (e.g. nvidia/nemotron-*) spend part of max_tokens thinking
# before they write the answer; without this allowance a summary stops
# mid-sentence. Models that don't reason stop well before the cap anyway.
REASONING_ALLOWANCE = 3000


_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


def check_reply(response, what: str) -> None:
    """Raise for an error sent inside a 200 reply; log a reply that was cut off.

    OpenRouter sometimes answers HTTP 200 with {"error": {"code": 503, ...}} and
    no choices (e.g. "Upstream error from Nvidia: Service temporarily
    overloaded"). The SDK doesn't raise for that, so it's raised here as the
    APIStatusError it stands for: ai_failure gives the matching message and the
    flashcard retry rules apply as for a real 503.
    """
    if not response.choices:
        error = getattr(response, "error", None) or {}
        code = error.get("code") if isinstance(error, dict) else None
        status = code if isinstance(code, int) and 400 <= code <= 599 else 502
        raise openai.APIStatusError(
            f"Error code: {status} - {error or 'reply without choices'}",
            response=httpx.Response(status, request=httpx.Request("POST", _COMPLETIONS_URL)),
            body=error or None,
        )
    if response.choices[0].finish_reason == "length":
        logger.warning(f"AI reply hit the length limit while {what} (model {MODEL_NAME}); the text is cut off")


def reply_text(response, what: str) -> str:
    """The reply's text. Raises for an error reply (see check_reply) and, as
    AIGenerationError, when there is no text (a reasoning model can use up the
    whole budget thinking); logs a reply that was cut off."""
    check_reply(response, what)
    text = (response.choices[0].message.content or "").strip()
    if not text:
        logger.warning(f"AI reply had no text while {what} (model {MODEL_NAME})")
        raise AIGenerationError("The AI returned an empty reply. Please try again.")
    return text


# A summary can take many calls (map-reduce, merged sets) and a single
# momentary failure would fail all of it, so temporary ones are retried.
TRANSIENT_RETRIES = 2
RETRY_DELAY_SECONDS = 2.0


def _is_transient(exc: BaseException) -> bool:
    """Overloaded / rate-limited / unreachable: worth another try. Key or credit problems aren't."""
    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
        return True
    if isinstance(exc, openai.APIStatusError):
        if is_daily_limit(exc):
            return False
        return exc.status_code == 429 or exc.status_code >= 500
    return False


def _complete(what: str, messages: list, temperature: float, max_tokens: int) -> str:
    """One summary AI call: the reply's text, retrying temporary failures.

    Raises AIGenerationError with a plain message (see ai_failure).
    """
    for attempt in range(TRANSIENT_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME, messages=messages, temperature=temperature, max_tokens=cap_tokens(max_tokens),
            )
            return reply_text(response, what)
        except AIGenerationError:
            raise
        except Exception as e:
            if attempt < TRANSIENT_RETRIES and _is_transient(e):
                logger.warning(f"AI call failed while {what} ({e}); retrying ({attempt + 1}/{TRANSIENT_RETRIES})")
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            raise ai_failure(e, what) from e


def _summarize_chunk(chunk_text: str) -> str:
    """Briefly summarize an individual chunk during the map step."""
    prompt = f"""You are an expert academic tutor. Extract key concepts, definitions, formulas, and main points from the text below as bullet points.

Text:
{chunk_text}

Summary Notes:"""

    return _complete(
        "summarizing a section",
        [
            {"role": "system", "content": "You are a concise academic tutor extracting high-yield study points."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=400 + REASONING_ALLOWANCE,
    )


# ─── Several AI calls at once ───
#
# A long source means one map call per ~3,000 characters (a 220,000-character
# textbook is ~75 calls); one after another that's several minutes. They're
# independent, so up to SUMMARY_PARALLEL_CALLS run at the same time. Each call
# keeps its own retries; a rate limit that survives them fails the summary as
# before.

DEFAULT_PARALLEL_CALLS = 4
MAX_PARALLEL_CALLS = 16


def parallel_calls() -> int:
    try:
        value = int(os.getenv("SUMMARY_PARALLEL_CALLS", "").strip())
    except ValueError:
        return DEFAULT_PARALLEL_CALLS
    return max(1, min(value, MAX_PARALLEL_CALLS))


def run_calls(fn, items) -> list:
    """fn(item) for every item, up to parallel_calls() at a time; results in the items' order.

    The first failure cancels the calls that haven't started and is raised
    (calls already running finish first, and their results are dropped).
    """
    items = list(items)
    workers = min(parallel_calls(), len(items))
    if workers <= 1:
        return [fn(item) for item in items]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fn, item) for item in items]
        try:
            return [future.result() for future in futures]
        except BaseException:
            for future in futures:
                future.cancel()
            raise


# ─── Notes too long for one final call: combine them in rounds ───
#
# The map step turns a long source into notes (about 1 call per 3,000
# characters), and one final call writes the summary from all of them. For a
# very long source or merged set the notes alone can exceed the model's
# context (gpt-3.5-turbo: 16k tokens), so they're combined in rounds first:
# grouped, each group condensed (keeping the [S12] labels), until they fit.

FALLBACK_FINAL_INPUT_CHARS = 24_000   # when the model's context size isn't known
MAX_FINAL_INPUT_CHARS = 200_000       # keeps the final call sensible on huge-context models
CHARS_PER_TOKEN = 3                   # conservative for English study text
PROMPT_OVERHEAD_TOKENS = 1_000        # system prompt, instructions, headings
COMBINE_GROUP_CHARS = 12_000          # notes per condensing call
COMBINE_MAX_TOKENS = 700
MAX_COMBINE_ROUNDS = 4
TOO_LONG_MESSAGE = "This material is too long to summarize in one go. Try fewer or smaller documents."


def final_input_budget(final_max_tokens: int) -> int:
    """How many characters of notes the final call can take for this model."""
    context = context_tokens()
    if not context:
        return FALLBACK_FINAL_INPUT_CHARS
    room = context - cap_tokens(final_max_tokens + REASONING_ALLOWANCE) - PROMPT_OVERHEAD_TOKENS
    return max(4_000, min(room * CHARS_PER_TOKEN, MAX_FINAL_INPUT_CHARS))


def _joined_len(parts: List[str]) -> int:
    return sum(len(p) for p in parts) + 2 * max(len(parts) - 1, 0)


def _split_long(text: str, size: int) -> List[str]:
    """Split text into pieces of at most `size` characters, at line breaks where possible."""
    if len(text) <= size:
        return [text]
    pieces, current = [], ""
    for line in text.split("\n"):
        while len(line) > size:  # a single very long line
            if current:
                pieces.append(current)
                current = ""
            pieces.append(line[:size])
            line = line[size:]
        if current and len(current) + 1 + len(line) > size:
            pieces.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        pieces.append(current)
    return pieces


def _condense(notes: str, cite: bool) -> str:
    system = "You are a concise academic tutor combining study notes into fewer, denser notes."
    if cite:
        system += " " + CITATION_RULE
    user = (
        "Combine the notes below into bullet points. Keep every key fact, definition and formula, "
        "and merge points that say the same thing. "
        + ("Keep the section labels ([S0], [S1], ...) of every point exactly as written. " if cite else "")
        + "Keep any 'Source N' headings.\n\nNotes:\n" + notes + "\n\nCombined notes:"
    )
    return _complete(
        "combining notes",
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.3,
        max_tokens=COMBINE_MAX_TOKENS + REASONING_ALLOWANCE,
    )


def fit_notes(parts: List[str], budget: int, cite: bool) -> List[str]:
    """Combine `parts` in rounds until they fit in `budget` characters together.

    Each round groups consecutive notes (never more than COMBINE_GROUP_CHARS
    per call) and condenses each group, so the notes shrink several times per
    round. Raises AIGenerationError(TOO_LONG_MESSAGE) if they still don't fit
    after MAX_COMBINE_ROUNDS.
    """
    rounds = 0
    while _joined_len(parts) > budget:
        if rounds >= MAX_COMBINE_ROUNDS:
            raise AIGenerationError(TOO_LONG_MESSAGE)
        size = min(COMBINE_GROUP_CHARS, budget)
        pieces = [piece for part in parts for piece in _split_long(part, size)]
        groups, current = [], []
        for piece in pieces:
            if current and _joined_len(current + [piece]) > size:
                groups.append(current)
                current = []
            current.append(piece)
        if current:
            groups.append(current)
        parts = run_calls(lambda group: _condense("\n\n".join(group), cite), groups)
        rounds += 1
    return parts


def generate_summary(document_text: str) -> str:
    """Generate an exam-revision summary of the document.

    If document_text exceeds MAP_REDUCE_THRESHOLD (~6000 chars), splits the text
    using RAGService.chunk_text, summarizes each chunk, and synthesizes into
    a single coherent summary under ~600 words.
    """
    if not document_text or not document_text.strip():
        return "No text content available to summarize."

    cleaned_text = document_text.strip()

    # Map-reduce if long document
    if len(cleaned_text) > MAP_REDUCE_THRESHOLD:
        chunks = RAGService.chunk_text(cleaned_text, chunk_size=3000, overlap=300)
        if len(chunks) > 1:
            chunks = [chunk for chunk in chunks if chunk.strip()]
            intermediate_summaries = [
                f"### Section {i + 1}\n{chunk_summary}"
                for i, chunk_summary in enumerate(run_calls(_summarize_chunk, chunks))
            ]
            source_content = "\n\n".join(fit_notes(intermediate_summaries, final_input_budget(900), cite=False))
        else:
            source_content = cleaned_text
    else:
        source_content = cleaned_text

    return _final_summary(source_content, SUMMARY_SYSTEM_PROMPT)


SUMMARY_SYSTEM_PROMPT = (
    "You are an expert study assistant creating an exam revision summary.\n"
    "Guidelines:\n"
    "1. Structure with clear Markdown headings and bullet points.\n"
    "2. Prominently highlight key definitions and essential formulas/equations.\n"
    "3. Explicitly call out any gaps or incomplete explanations found in the source text (e.g., 'Note: this document does not explain X in depth').\n"
    "4. Keep the entire summary concise and strictly under 600 words.\n"
    "5. Output clean Markdown only."
)


def _final_summary(source_content: str, system_prompt: str, max_tokens: int = 900) -> str:
    user_prompt = f"""Generate a high-yield exam revision summary based on the following material:

{source_content}

Exam Revision Summary:"""

    return _complete(
        "generating a summary",
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=max_tokens + REASONING_ALLOWANCE,
    )


def append_source_link(summary: str, title: str, url: str) -> str:
    """Add a 'Source: [title](url)' footer, built from stored data, never by the model."""
    safe_title = re.sub(r"([\[\]\\])", r"\\\1", title.strip() or url)
    safe_url = url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
    return f"{summary.rstrip()}\n\n---\n\nSource: [{safe_title}]({safe_url})"


# ─── YouTube summaries with timestamp citations ───
#
# The model never writes times, pages or slide numbers itself. Each stored
# chunk is labelled [S0], [S1], ... and the model cites those labels;
# replace_labels() then swaps each label for that chunk's citation, built from
# stored data: a [mm:ss](url&t=...) link for YouTube, "(p. 12)" for PDFs,
# "(Slide 4)" for PowerPoint. A label the model invents that matches no chunk
# (or a chunk with no citation) is dropped, so every citation that survives
# points at a real place in the source.

# One match = a run of labels like "[S3]", "[S3, S7]" or "[S3][S7]", so the
# citations for a run are joined (and de-duplicated) together. Some models
# Markdown-escape the brackets ("\[S3\]"); the backslashes are matched too so
# they're replaced along with the label.
_LABEL = r"\\?\[\s*S\d+(?:\s*,\s*S\d+)*\s*\\?\]"
_CITATION_RE = re.compile(rf"{_LABEL}(?:[ \t]*{_LABEL})*")
# A run the model put in its own parentheses: "([S3])" would become "((p. 12))".
_WRAPPED_CITATION_RE = re.compile(rf"\(\s*({_LABEL}(?:[ \t]*{_LABEL})*)\s*\)")

CITATION_RULE = (
    "The material is split into sections labelled [S0], [S1], [S2], ... "
    "End EVERY bullet point with the label(s) of the section(s) it came from, "
    "exactly as written, e.g. '- Photosynthesis happens in chloroplasts [S3]' "
    "or '... [S3][S7]'. Never write times, timestamps, page numbers or slide numbers yourself; "
    "use only the labels."
)

# (label, url) for a chunk: url is None for citations that aren't links (pages, slides).
Citation = Optional[Tuple[str, Optional[str]]]


def format_timestamp(seconds: int) -> str:
    """125 -> '02:05'; 3725 -> '1:02:05'."""
    h, rem = divmod(max(int(seconds), 0), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def format_pages(page_start: Optional[int], page_end: Optional[int]) -> Optional[str]:
    """(12, 12) -> 'p. 12'; (12, 13) -> 'pp. 12–13'; unknown pages -> None."""
    if page_start is None:
        return None
    if page_end is None or page_end == page_start:
        return f"p. {page_start}"
    return f"pp. {page_start}–{page_end}"


def replace_labels(text: str, citations: List[Citation], join_plain=None) -> str:
    """Replace [S<i>] labels with each chunk's citation.

    Linked citations become Markdown links separated by spaces
    ("[02:05](url) [03:10](url)"); plain ones are joined in one bracket
    ("(p. 3; pp. 7–8)"), or by `join_plain(labels)` if given (merged
    summaries group them by source). Repeats within a run are dropped.
    """
    join_plain = join_plain or "; ".join

    def render(run: str):
        links, plain, seen = [], [], set()
        for idx in (int(n) for n in re.findall(r"S(\d+)", run)):
            citation = citations[idx] if idx < len(citations) else None
            if citation is None or citation in seen:
                continue
            seen.add(citation)
            label, url = citation
            if url:
                links.append(f"[{label}]({url})")
            else:
                plain.append(label)
        return links, plain

    def replace(match: re.Match) -> str:
        links, plain = render(match.group(0))
        return " ".join(links + ([f"({join_plain(plain)})"] if plain else []))

    def replace_wrapped(match: re.Match) -> str:
        # Keep one pair of parentheses: plain citations bring their own, links get one.
        links, plain = render(match.group(1))
        if plain:
            return " ".join(links + [f"({join_plain(plain)})"])
        return f"({' '.join(links)})" if links else ""

    replaced = _CITATION_RE.sub(replace, _WRAPPED_CITATION_RE.sub(replace_wrapped, text))
    # Dropping an invalid label can leave a trailing space before a newline.
    return re.sub(r"[ \t]+$", "", replaced, flags=re.MULTILINE)


def link_citations(text: str, start_seconds: List[int], source_url: str) -> str:
    """Replace [S<i>] labels with Markdown timestamp links into the video."""
    return replace_labels(text, [
        (format_timestamp(s), YouTubeService.generate_timestamp_url(source_url, s)) for s in start_seconds
    ])


def _summarize_labelled_batch(labelled_text: str) -> str:
    """Map step for long sources: bullet notes that keep their [S<i>] labels."""
    return _complete(
        "summarizing a section",
        [
            {"role": "system", "content": "You are a concise academic tutor extracting high-yield study points. " + CITATION_RULE},
            {"role": "user", "content": f"Extract key concepts, definitions, formulas, and main points as bullet points.\n\nText:\n{labelled_text}\n\nSummary Notes:"},
        ],
        temperature=0.3,
        max_tokens=400 + REASONING_ALLOWANCE,
    )


def generate_cited_summary(chunks: List[str], citations: List[Citation]) -> str:
    """Exam-revision summary where every point cites where it came from.

    `chunks` are the stored chunk texts in source order and `citations[i]`
    is the citation for chunks[i] (see replace_labels).
    """
    if not chunks:
        return "No text content available to summarize."

    labelled = [f"[S{i}] {text.strip()}" for i, text in enumerate(chunks)]

    if sum(len(block) + 2 for block in labelled) <= MAP_REDUCE_THRESHOLD:
        source_content = "\n\n".join(labelled)
    else:
        # Batch whole labelled chunks (never split one, so labels stay intact).
        batches, current, current_len = [], [], 0
        for block in labelled:
            if current and current_len + len(block) > 3000:
                batches.append(current)
                current, current_len = [], 0
            current.append(block)
            current_len += len(block) + 2
        if current:
            batches.append(current)
        notes = [
            f"### Part {i + 1}\n{note}"
            for i, note in enumerate(run_calls(lambda batch: _summarize_labelled_batch("\n".join(batch)), batches))
        ]
        source_content = "\n\n".join(fit_notes(notes, final_input_budget(900), cite=True))

    system_prompt = (
        SUMMARY_SYSTEM_PROMPT
        + "\n6. " + CITATION_RULE
        + " Keep the labels from the material when you combine or rephrase points."
    )
    summary = _final_summary(source_content, system_prompt)
    return replace_labels(summary, citations)


def generate_youtube_summary(chunks: List[Tuple[int, str]], source_url: str) -> str:
    """Exam-revision summary of a video where every point links to its moment.

    `chunks` is [(start_seconds, text), ...] in video order.
    """
    return generate_cited_summary(
        [text for _, text in chunks],
        [(format_timestamp(s), YouTubeService.generate_timestamp_url(source_url, s)) for s, _ in chunks],
    )
