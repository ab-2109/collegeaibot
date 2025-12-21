"""OpenAI client factory and model configuration.

This keeps the dependency on the OpenAI SDK in one place, which makes
it easier to swap or mock in tests, or to plug into LangGraph later.

Environment variables (e.g. ``OPENAI_API_KEY``) are loaded from a
``.env`` file if present, using ``python-dotenv``. This lets you keep
API keys in `.env` without exporting them manually each time.
"""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
import httpx
from openai import OpenAI


# Load environment variables from a .env file if it exists.
load_dotenv()


DEFAULT_MODEL = os.getenv("COLLEGEAIBOT_MODEL", "gpt-5.2")

# Default request timeout (seconds) to avoid hanging forever.
DEFAULT_TIMEOUT_S = float(os.getenv("COLLEGEAIBOT_TIMEOUT_S", "60"))


def get_openai_client(api_key: Optional[str] = None) -> OpenAI:
    """Return an OpenAI client configured from environment or explicit key.

    The OpenAI Python SDK already respects the OPENAI_API_KEY environment
    variable; this helper simply centralizes construction so it can be
    reused across modules and tests.
    """

    http_client = httpx.Client(timeout=httpx.Timeout(DEFAULT_TIMEOUT_S))

    if api_key is not None:
        return OpenAI(api_key=api_key, http_client=http_client)

    # Fallback to env configuration (OPENAI_API_KEY, etc.).
    return OpenAI(http_client=http_client)
