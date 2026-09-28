"""
AI-powered Document Summarization Service.

Generates structured, exam-revision summaries using OpenRouter.
For documents longer than ~6000 characters, uses a chunk-and-map-reduce approach
to avoid context overflow and provide a coherent, high-yield summary.
"""

import logging
import os
import re
from typing import List, Tuple
import openai
from dotenv import load_dotenv
from openai import OpenAI

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
    429: "The AI service is busy right now (rate limit reached). Please wait a minute and try again.",
}


def ai_error_message(exc: BaseException) -> str:
    """Turn an OpenAI/OpenRouter failure into a plain message for the user."""
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

MODEL_NAME = "openai/gpt-3.5-turbo"
MAP_REDUCE_THRESHOLD = 6000


def _summarize_chunk(chunk_text: str) -> str:
    """Briefly summarize an individual chunk during the map step."""
    prompt = f"""You are an expert academic tutor. Extract key concepts, definitions, formulas, and main points from the text below as bullet points.

Text:
{chunk_text}

Summary Notes:"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a concise academic tutor extracting high-yield study points."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=400,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise ai_failure(e, "summarizing a section") from e


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


def _final_summary(source_content: str, system_prompt: str) -> str:
    user_prompt = f"""Generate a high-yield exam revision summary based on the following material:

{source_content}

Exam Revision Summary:"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=900,
        )
        return response.choices[0].message.content.strip()
    except AIGenerationError:
        raise
    except Exception as e:
        raise ai_failure(e, "generating a summary") from e


def append_source_link(summary: str, title: str, url: str) -> str:
    """Add a 'Source: [title](url)' footer, built from stored data, never by the model."""
    safe_title = re.sub(r"([\[\]\\])", r"\\\1", title.strip() or url)
    safe_url = url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
    return f"{summary.rstrip()}\n\n---\n\nSource: [{safe_title}]({safe_url})"


# ─── YouTube summaries with timestamp citations ───
#
# The model never writes times itself. Each transcript chunk is labelled
# [S0], [S1], ... and the model cites those labels; link_citations() then
# swaps each label for a [mm:ss](url&t=...) link built from that chunk's
# stored start_seconds. A label the model invents that matches no chunk is
# dropped, so every link that survives points at a real moment in the video.

# One match = a run of labels like "[S3]", "[S3, S7]" or "[S3][S7]", so the
# links for a run are joined (and de-duplicated) together.
_LABEL = r"\[\s*S\d+(?:\s*,\s*S\d+)*\s*\]"
_CITATION_RE = re.compile(rf"{_LABEL}(?:[ \t]*{_LABEL})*")

CITATION_RULE = (
    "The material is split into sections labelled [S0], [S1], [S2], ... "
    "End EVERY bullet point with the label(s) of the section(s) it came from, "
    "exactly as written, e.g. '- Photosynthesis happens in chloroplasts [S3]' "
    "or '... [S3][S7]'. Never write times or timestamps yourself; use only the labels."
)


def format_timestamp(seconds: int) -> str:
    """125 -> '02:05'; 3725 -> '1:02:05'."""
    h, rem = divmod(max(int(seconds), 0), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def link_citations(text: str, start_seconds: List[int], source_url: str) -> str:
    """Replace [S<i>] labels with Markdown timestamp links into the video."""

    def replace(match: re.Match) -> str:
        links = []
        seen = set()
        for idx in (int(n) for n in re.findall(r"S(\d+)", match.group(0))):
            if idx >= len(start_seconds) or idx in seen:
                continue
            seen.add(idx)
            url = YouTubeService.generate_timestamp_url(source_url, start_seconds[idx])
            links.append(f"[{format_timestamp(start_seconds[idx])}]({url})")
        return " ".join(links)

    linked = _CITATION_RE.sub(replace, text)
    # Dropping an invalid label can leave a trailing space before a newline.
    return re.sub(r"[ \t]+$", "", linked, flags=re.MULTILINE)


def _summarize_labelled_batch(labelled_text: str) -> str:
    """Map step for long videos: bullet notes that keep their [S<i>] labels."""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a concise academic tutor extracting high-yield study points. " + CITATION_RULE},
                {"role": "user", "content": f"Extract key concepts, definitions, formulas, and main points as bullet points.\n\nText:\n{labelled_text}\n\nSummary Notes:"},
            ],
            temperature=0.3,
            max_tokens=400,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise ai_failure(e, "summarizing a section") from e


def generate_youtube_summary(chunks: List[Tuple[int, str]], source_url: str) -> str:
    """Exam-revision summary of a video where every point links to its moment.

    `chunks` is [(start_seconds, text), ...] in video order.
    """
    if not chunks:
        return "No text content available to summarize."

    start_seconds = [s for s, _ in chunks]
    labelled = [f"[S{i}] {text.strip()}" for i, (_, text) in enumerate(chunks)]

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
    return link_citations(summary, start_seconds, source_url)
