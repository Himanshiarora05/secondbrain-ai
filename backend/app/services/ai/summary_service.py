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
from typing import List, Optional, Tuple
import httpx
import openai
from dotenv import load_dotenv
from openai import OpenAI

from app.services.ai.model_limits import cap_tokens
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
            intermediate_summaries = []
            for i, chunk in enumerate(chunks):
                if chunk.strip():
                    chunk_summary = _summarize_chunk(chunk)
                    intermediate_summaries.append(f"### Section {i + 1}\n{chunk_summary}")
            source_content = "\n\n".join(intermediate_summaries)
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
        source_content = "\n\n".join(
            f"### Part {i + 1}\n{_summarize_labelled_batch(chr(10).join(batch))}"
            for i, batch in enumerate(batches)
        )

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
