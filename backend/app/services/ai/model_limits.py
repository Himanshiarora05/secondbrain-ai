"""
The configured model's limits, from OpenRouter's public model list.

Models differ a lot: openai/gpt-3.5-turbo has a 16,385-token context and at
most 4,096 output tokens, while openai/gpt-4o-mini has 128,000 and 16,384.
Asking for more output than a model allows makes the call fail, so every AI
call caps its max_tokens with cap_tokens(), and long summaries size their
final step from context_tokens().

Loaded once at start-up (main.py) with one GET to the public list, which needs
no API key. If that fails (offline, OpenRouter down), or nothing loaded them
(tests), calls are capped at FALLBACK_MAX_OUTPUT and the context is unknown,
so callers use their conservative defaults.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

MODELS_URL = "https://openrouter.ai/api/v1/models"
# gpt-3.5-turbo's output limit: safe for every model the app has used.
FALLBACK_MAX_OUTPUT = 4096

_limits = {"model": None, "context": None, "max_output": None}


def load_model_limits(model: str, client: Optional[httpx.Client] = None) -> dict:
    """Fetch and keep `model`'s context size and max output tokens. Never raises."""
    _limits.update(model=model, context=None, max_output=None)
    try:
        own_client = client is None
        client = client or httpx.Client(timeout=15)
        try:
            response = client.get(MODELS_URL)
            response.raise_for_status()
            body = response.json()
            entries = body.get("data") if isinstance(body, dict) else None
            if not isinstance(entries, list):
                raise ValueError("unexpected response shape")
            entries = [m for m in entries if isinstance(m, dict)]
        finally:
            if own_client:
                client.close()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"Could not load limits for {model} from OpenRouter ({e}); capping output at {FALLBACK_MAX_OUTPUT} tokens.")
        return dict(_limits)

    entry = next((m for m in entries if m.get("id") == model), None)
    if entry is None:
        logger.warning(f"{model} isn't in OpenRouter's model list; capping output at {FALLBACK_MAX_OUTPUT} tokens.")
        return dict(_limits)
    context = entry.get("context_length")
    max_output = (entry.get("top_provider") or {}).get("max_completion_tokens")
    _limits["context"] = int(context) if context else None
    _limits["max_output"] = int(max_output) if max_output else None
    return dict(_limits)


def context_tokens() -> Optional[int]:
    return _limits["context"]


def max_output_tokens() -> int:
    """The model's output limit, or FALLBACK_MAX_OUTPUT when it isn't known."""
    return _limits["max_output"] or FALLBACK_MAX_OUTPUT


def cap_tokens(requested: int) -> int:
    return min(requested, max_output_tokens())
