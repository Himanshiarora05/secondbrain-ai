"""
AI-generated multiple-choice quizzes, with citations like flashcards.

Same rules as cited flashcards (flashcard_service): the stored chunks are
labelled [S0], [S1], ...; the model gives each question the ONE label it came
from, and the citation (page, slide, timestamp link, page link) is built here
from stored data. Coverage is enforced in code with the flashcards' batching
(plan_batches / pick_across_batches).

Each question has exactly 4 distinct options and one correct answer. The
options are shuffled in code, because models put the right answer first far
more often than chance.
"""

import json
import os
import random
import re
from typing import Dict, List, Optional

import openai
from dotenv import load_dotenv
from openai import OpenAI

from app.services.ai.flashcard_service import (
    Citation,
    citation_fields,
    labelled_batch,
    pick_across_batches,
    plan_batches,
)
from app.services.ai.model_limits import cap_tokens
from app.services.ai.summary_service import (
    MODEL_NAME, REASONING_ALLOWANCE, AIGenerationError, ai_failure, check_reply, is_daily_limit,
)
from app.services.rag.rag_service import RAGService

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    timeout=45,
)

DEFAULT_QUESTIONS = 10
OPTIONS = 4
LETTERS = "ABCD"
# Replaced in tests for a fixed order.
_rng = random.Random()

QUIZ_SYSTEM_PROMPT = (
    "You are an expert exam tutor writing multiple-choice questions that test understanding of study material.\n"
    "Return STRICT JSON only: an array of objects with the keys 'question', 'options', 'answer', 'explanation' "
    "and 'source'.\n"
    "Rules:\n"
    "- 'options' is a list of exactly 4 different answer texts. Exactly one is correct; the other three are "
    "plausible but clearly wrong according to the material.\n"
    "- 'answer' is the letter of the correct option: \"A\", \"B\", \"C\" or \"D\".\n"
    "- 'explanation' says in 1-2 sentences why the correct answer is right, based on the material.\n"
    "- Ask about key concepts, definitions, formulas and facts the material actually states. Never ask about "
    "anything it doesn't cover.\n"
    "- Don't write 'All of the above' or 'None of the above', and don't put letters in front of the options.\n"
    "- Write formulas in plain text or Unicode (e.g. x₁ + x₂), not LaTeX.\n"
    "- The material is split into sections labelled [S0], [S1], [S2], ... Give each question a 'source' key with "
    "the ONE label of the section it came from, exactly as written, e.g. \"source\": \"S3\". Never write times, "
    "page numbers or URLs yourself.\n"
    "- Spread the questions across ALL the sections, from the first to the last.\n"
    "- Do NOT include any intro, outro, or markdown code blocks. Output ONLY raw JSON: "
    '[{"question": "...", "options": ["...", "...", "...", "..."], "answer": "B", "explanation": "...", "source": "S0"}]'
)

_LETTER_PREFIX_RE = re.compile(r"^\(?[A-Da-d][\).:]\s+")


def _correct_index(raw, options: List[str]) -> Optional[int]:
    """The model's 'answer' ("B", "b)", 1, or the option's text) as an index into options."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if 0 <= raw < len(options) else None
    text = str(raw or "").strip()
    if not text:
        return None
    letter = re.fullmatch(r"\(?([A-Da-d])[\).:]?", text)
    if letter:
        return LETTERS.index(letter.group(1).upper())
    lowered = [o.lower() for o in options]
    cleaned = _LETTER_PREFIX_RE.sub("", text).lower()
    return lowered.index(cleaned) if cleaned in lowered else None


def _clean_question(item) -> Optional[Dict]:
    """A usable question, or None: a question, 4 distinct options, a valid answer."""
    if not isinstance(item, dict):
        return None
    question = str(item.get("question") or "").strip()
    raw_options = item.get("options")
    if not question or not isinstance(raw_options, list):
        return None
    options = [_LETTER_PREFIX_RE.sub("", str(o).strip()) for o in raw_options]
    if len(options) != OPTIONS or not all(options) or len({o.lower() for o in options}) != OPTIONS:
        return None
    correct = _correct_index(item.get("answer"), options)
    if correct is None:
        return None
    return {
        "question": question,
        "options": options,
        "correct_index": correct,
        "explanation": str(item.get("explanation") or "").strip(),
        "source": item.get("source"),
    }


def parse_quiz_json(raw_text: str) -> List[Dict]:
    """Questions from the model's reply; malformed ones are dropped. Raises ValueError if it isn't JSON."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse quiz JSON: {raw_text[:200]}") from e
    if not isinstance(data, list):
        raise ValueError("Quiz response is not a list")
    return [q for q in (_clean_question(item) for item in data) if q]


def shuffle_options(question: Dict, rng: random.Random) -> Dict:
    """The same question with its options in random order (correct_index follows its option)."""
    order = list(range(len(question["options"])))
    rng.shuffle(order)
    return {
        **question,
        "options": [question["options"][i] for i in order],
        "correct_index": order.index(question["correct_index"]),
    }


def _generate_questions_from_text(labelled_text: str, count: int) -> List[Dict]:
    """One call (retried once) for `count` questions about labelled material."""
    user_prompt = (
        f"Write {count} multiple-choice questions based on the following material:\n\n"
        f"{labelled_text}\n\nSTRICT JSON QUESTIONS:"
    )
    last_exception = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4 if attempt == 0 else 0.2,
                max_tokens=cap_tokens(250 * count + 400 + REASONING_ALLOWANCE),
            )
            check_reply(response, "generating the quiz")
            questions = parse_quiz_json(response.choices[0].message.content or "")
            if questions:
                return questions
            last_exception = ValueError("LLM returned no usable questions")
        except openai.APIStatusError as e:
            if e.status_code in (401, 402, 403) or is_daily_limit(e):  # a retry can't help
                raise ai_failure(e, "generating the quiz") from e
            last_exception = e
        except Exception as e:
            last_exception = e

    if isinstance(last_exception, ValueError):  # the model answered, but not with usable questions
        raise AIGenerationError("The AI returned the quiz in an unexpected format. Please try again.")
    raise ai_failure(last_exception, "generating the quiz") from last_exception


def generate_cited_quiz(chunks: List[str], citations: List[Citation], count: int = DEFAULT_QUESTIONS) -> List[Dict]:
    """Up to `count` questions spread across the source, in source order, each citing its chunk.

    Returns [{"question", "options", "correct_index", "explanation", "source_label", "source_url"}, ...].
    Raises AIGenerationError with a plain message.
    """
    texts = [(c or "").strip() for c in chunks]
    if not any(texts):
        return []
    batches, per_batch = plan_batches(texts, count)
    per_batch_questions: List[List[Dict]] = []
    for batch in batches:
        raw = _generate_questions_from_text(labelled_batch(texts, batch), per_batch)
        per_batch_questions.append([
            {
                **shuffle_options({k: q[k] for k in ("question", "options", "correct_index", "explanation")}, _rng),
                **citation_fields(q.get("source"), batch, citations),
            }
            for q in raw
        ])
    return pick_across_batches(per_batch_questions, count)


def generate_quiz(document_text: str, count: int = DEFAULT_QUESTIONS) -> List[Dict]:
    """For a document without stored chunks: its text, chunked here, with no citations."""
    chunks = RAGService.chunk_text((document_text or "").strip())
    return generate_cited_quiz(chunks, [None] * len(chunks), count=count)
