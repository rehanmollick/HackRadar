"""OpenRouter provider — last-ditch fallback for Pass 1 + Pass 2.

OpenRouter exposes dozens of free-tier hosted models behind an
OpenAI-compatible /chat/completions endpoint. We use it as the outer
ring of the fallback chain so that even when Cerebras AND Groq are
both rate-limited, the scan still completes.

Default model picks (2026-04-08 free-tier survey):
  Pass 1: meta-llama/llama-3.3-70b-instruct:free  (fast 70B triage)
  Pass 2: openai/gpt-oss-120b:free                (beefy scoring model)

OpenRouter requires two extra headers for free-tier access:
  HTTP-Referer: identifies the calling app
  X-Title:      shows up in OpenRouter's dashboard/leaderboards
"""

from __future__ import annotations

from typing import AsyncIterator, Type, TypeVar

from pydantic import BaseModel

from hackradar import config
from hackradar.models import Item
from hackradar.scoring.providers._openai_compat import call_chat_json
from hackradar.scoring.providers.base import ProviderError

T = TypeVar("T", bound=BaseModel)

BASE_URL = "https://openrouter.ai/api/v1"

# OpenRouter asks for these for free-tier attribution.
_EXTRA_HEADERS = {
    "HTTP-Referer": "https://github.com/rehanmollick/HackRadar",
    "X-Title": "HackRadar",
}


class OpenRouterProvider:
    """Free-tier OpenRouter fallback. Model is configurable per instance."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        name: str | None = None,
    ):
        self.model = model
        self.api_key = api_key or config.OPENROUTER_API_KEY
        # Friendly display name for logs: "openrouter_gpt-oss-120b"
        slug = model.split("/")[-1].split(":")[0]
        self.name = name or f"openrouter_{slug}"

    async def call_batch(
        self,
        items: list[Item],
        prompt: str,
        response_schema: Type[T],
    ) -> T:
        if not self.api_key:
            raise ProviderError("OPENROUTER_API_KEY is not set")

        return await call_chat_json(
            base_url=BASE_URL,
            api_key=self.api_key,
            model=self.model,
            prompt=prompt,
            response_schema=response_schema,
            max_tokens=4096,
            extra_headers=_EXTRA_HEADERS,
        )

    async def chat_stream(self, messages: list[dict], system: str) -> AsyncIterator[str]:
        raise NotImplementedError("OpenRouterProvider does not implement chat_stream")
        yield  # pragma: no cover
