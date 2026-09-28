"""
AI-powered Document Summarization Service.

Generates structured, exam-revision summaries using OpenRouter.
For documents longer than ~6000 characters, uses a chunk-and-map-reduce approach
to avoid context overflow and provide a coherent, high-yield summary.
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

from app.services.rag.rag_service import RAGService

load_dotenv()


class AIGenerationError(Exception):
    """Raised when AI generation fails via OpenAI / OpenRouter."""
    pass


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
        raise AIGenerationError(f"Failed to summarize a section: {e}") from e


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

    system_prompt = (
        "You are an expert study assistant creating an exam revision summary.\n"
        "Guidelines:\n"
        "1. Structure with clear Markdown headings and bullet points.\n"
        "2. Prominently highlight key definitions and essential formulas/equations.\n"
        "3. Explicitly call out any gaps or incomplete explanations found in the source text (e.g., 'Note: this document does not explain X in depth').\n"
        "4. Keep the entire summary concise and strictly under 600 words.\n"
        "5. Output clean Markdown only."
    )

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
        raise AIGenerationError(f"Failed to generate summary: {str(e)}") from e
