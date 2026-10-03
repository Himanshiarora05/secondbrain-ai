"""
Text recognition (OCR) with an OpenRouter vision model.

Used for PDF pages that have no text layer (scanned pages) and for uploaded
photos / screenshots of notes. Each page or image is one AI call that returns
its text; the calls run through run_calls (SUMMARY_PARALLEL_CALLS at a time).

The model is OCR_MODEL from backend/.env, else DEFAULT_OCR_MODEL (a free model
that accepts images). Free models come and go on OpenRouter: if the default
disappears (404 "model isn't available"), set OCR_MODEL to another model whose
input modalities include "image". Read at import, so a change needs a restart.
"""

import base64
import io
import logging
import os
import time
from typing import List, Optional, Tuple

import openai
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageOps, UnidentifiedImageError

from app.services.ai.summary_service import (
    AIGenerationError,
    RETRY_DELAY_SECONDS,
    TRANSIENT_RETRIES,
    _is_transient,
    ai_failure,
    check_reply,
    run_calls,
)

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_OCR_MODEL = "google/gemma-4-31b-it:free"
OCR_MODEL = os.getenv("OCR_MODEL", "").strip() or DEFAULT_OCR_MODEL

# Pages (scanned PDF pages, or images) read by OCR in one upload: one AI call
# each, and free models allow about 20 requests a minute and 50 a day.
MAX_OCR_PAGES = 20

# Images are shrunk to this longest side before they're sent: enough for
# printed and handwritten text, and keeps each request well under the limits.
MAX_IMAGE_SIDE = 2000
JPEG_QUALITY = 85
# Scanned PDF pages are rendered at this resolution (an A4 page ≈ 1240 × 1750).
PDF_RENDER_DPI = 150
OCR_MAX_TOKENS = 4096

# Vision calls take longer than text calls, especially on free models.
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    timeout=120,
)

OCR_PROMPT = (
    "Transcribe all the text in this image exactly as written, in reading order. "
    "Keep headings, lists and line breaks; write tables row by row and formulas in plain text. "
    "Don't describe, summarise or correct anything, and don't add any commentary. "
    "Transcribe only the actual notes: leave out browser and app interface text "
    "(such as \"Press Esc to exit full screen\", tabs, toolbars and menus), watermarks and logos. "
    "If the image contains no text, reply with nothing at all."
)

# What a model writes when told to reply with nothing, but writes something anyway.
_NO_TEXT_REPLIES = {"", "nothing", "(nothing)", "[nothing]", "no text", "[no text]", "(no text)"}

TOO_MANY_PAGES_MESSAGE = (
    "Text recognition is limited to {limit} pages per upload, and this upload needs {count}. "
    "Split it into parts of {limit} pages or fewer and upload each one."
)

MODEL_UNAVAILABLE_MESSAGE = (
    "The text recognition model ({model}) isn't available. Set OCR_MODEL in backend/.env to another "
    "OpenRouter model that accepts images, and check your OpenRouter privacy settings."
)


class ImageFileError(ValueError):
    """An uploaded file isn't a JPEG or PNG image that can be read."""


def prepare_image(data: bytes) -> bytes:
    """A JPEG (or PNG) upload as a JPEG ready for the model.

    Turned upright (phone photos are often stored sideways with an EXIF
    rotation), converted to RGB and shrunk to MAX_IMAGE_SIDE. Raises
    ImageFileError if it isn't a readable JPEG or PNG.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ("JPEG", "PNG"):
                raise ImageFileError(f"unsupported image format {image.format}")
            image.load()
            image = ImageOps.exif_transpose(image)
            if image.mode in ("RGBA", "LA", "P"):
                # Transparent screenshots: put them on white, not black.
                rgba = image.convert("RGBA")
                image = Image.new("RGB", rgba.size, "white")
                image.paste(rgba, mask=rgba.getchannel("A"))
            else:
                image = image.convert("RGB")
            image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=JPEG_QUALITY)
            return out.getvalue()
    except ImageFileError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        raise ImageFileError(str(e)) from e


def _clean(text: str) -> str:
    text = text.strip()
    # Some models wrap the transcription in a code fence.
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3]
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.strip()
    return "" if text.lower() in _NO_TEXT_REPLIES else text


def ocr_image(jpeg: bytes, what: str = "reading text from an image") -> str:
    """The text in one JPEG image ("" when there is none).

    Retries temporary failures like summary calls; raises AIGenerationError
    with a plain message (see ai_failure).
    """
    url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": OCR_PROMPT},
            {"type": "image_url", "image_url": {"url": url}},
        ],
    }]
    for attempt in range(TRANSIENT_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=OCR_MODEL, messages=messages, temperature=0, max_tokens=OCR_MAX_TOKENS,
            )
            check_reply(response, what)
            return _clean(response.choices[0].message.content or "")
        except AIGenerationError:
            raise
        except Exception as e:
            if attempt < TRANSIENT_RETRIES and _is_transient(e):
                logger.warning(f"OCR call failed while {what} ({e}); retrying ({attempt + 1}/{TRANSIENT_RETRIES})")
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            if isinstance(e, openai.APIStatusError) and e.status_code == 404:
                # ai_failure would point at OPENROUTER_MODEL, the wrong setting here.
                logger.warning(f"OCR model {OCR_MODEL} unavailable while {what}: {e}")
                raise AIGenerationError(MODEL_UNAVAILABLE_MESSAGE.format(model=OCR_MODEL)) from e
            raise ai_failure(e, what) from e


def ocr_images(jpegs: List[bytes], page_numbers: Optional[List[int]] = None) -> List[str]:
    """The text of each image, in order. `page_numbers` only label the log
    messages (default 1, 2, ...). Raises AIGenerationError if any call fails."""
    numbered: List[Tuple[int, bytes]] = list(zip(page_numbers or range(1, len(jpegs) + 1), jpegs))
    return run_calls(lambda item: ocr_image(item[1], f"reading text from page {item[0]}"), numbered)
