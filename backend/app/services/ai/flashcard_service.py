"""
AI-powered Flashcard Generation Service.

Generates strict JSON flashcard decks for exam revision.
Includes defensive JSON parsing and map-reduce chunking for long documents.
"""

import json
import re
import os
from typing import List, Dict
from dotenv import load_dotenv
from openai import OpenAI

from app.services.rag.rag_service import RAGService
from app.services.ai.summary_service import AIGenerationError

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    timeout=30,
)

MODEL_NAME = "openai/gpt-3.5-turbo"
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
                validated.append({"question": q, "answer": a})

    return validated


def _generate_flashcards_from_text(text_segment: str, count: int) -> List[Dict[str, str]]:
    """Single-pass call to generate flashcards from text."""
    system_prompt = (
        "You are an expert exam tutor creating flashcards for spaced repetition study.\n"
        "Return STRICT JSON only — an array of objects, each with 'question' and 'answer' keys.\n"
        "Rules:\n"
        "- Focus on high-yield exam facts, core definitions, formulas, and key concepts.\n"
        "- Keep questions direct and specific.\n"
        "- Keep answers clear, accurate, and concise (1-3 sentences).\n"
        "- Do NOT include any intro, outro, or markdown code blocks. Output ONLY raw JSON: [{\"question\": \"...\", \"answer\": \"...\"}]"
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
                max_tokens=1200,
            )
            content = response.choices[0].message.content or ""
            cards = _parse_flashcard_json(content)
            if cards:
                return cards
            last_exception = ValueError("LLM returned empty or unparseable flashcards")
        except Exception as e:
            last_exception = e
            if attempt == 1:
                print(f"Error generating flashcards on attempt {attempt}: {e}")

    raise AIGenerationError(f"Failed to generate flashcards: {last_exception}")


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
