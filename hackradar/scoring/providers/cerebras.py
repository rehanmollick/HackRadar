"""Cerebras provider — Pass 2 scoring using Qwen3 32B.

Cerebras free tier: ~30 RPM, 1M tokens/day, 8K context window on Qwen3 32B.
Per-item budget: ~1.5K system + ~1.2K item + ~1.2K response = ~2.4K per slot.
3 items/batch + system = ~6.5K, safe headroom below 8K.

We enforce the context ceiling CLIENT-SIDE before calling the API so an
oversized batch raises ContextOverflowError instead of burning a round-trip.
"""

from __future__ import annotations

from typing import AsyncIterator, Type, TypeVar

from pydantic import BaseModel

from hackradar import config
from hackradar.models import Item
from hackradar.scoring.prompts import estimate_tokens
from hackradar.scoring.providers._openai_compat import call_chat_json
from hackradar.scoring.providers.base import ContextOverflowError, ProviderError

T = TypeVar("T", bound=BaseModel)

BASE_URL = "https://api.cerebras.ai/v1"

# Hard ceiling below the 8K context window to leave room for the response.
CONTEXT_BUDGET_TOKENS = 7500


class CerebrasProvider:
    name = "cerebras"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or config.PASS2_MODEL
        self.api_key = api_key or config.CEREBRAS_API_KEY

    async def call_batch(
        self,
        items: list[Item],
        prompt: str,
        response_schema: Type[T],
    ) -> T:
        if not self.api_key:
            raise ProviderError("CEREBRAS_API_KEY is not set")

        # Client-side context budget check. Estimates reserve ~1.2K per item
        # for the response on top of the prompt itself.
        prompt_tokens = estimate_tokens(prompt)
        response_reserve = 1200 * max(1, len(items))
        total = prompt_tokens + response_reserve
        if total > CONTEXT_BUDGET_TOKENS:
            raise ContextOverflowError(
                f"{self.model}: batch of {len(items)} items estimated at "
                f"{total} tokens (prompt={prompt_tokens}, reserve={response_reserve}) "
                f"exceeds context budget {CONTEXT_BUDGET_TOKENS}"
            )

        return await call_chat_json(
            base_url=BASE_URL,
            api_key=self.api_key,
            model=self.model,
            prompt=prompt,
            response_schema=response_schema,
            max_tokens=response_reserve,
        )

    async def chat_stream(self, messages: list[dict], system: str) -> AsyncIterator[str]:
        raise NotImplementedError("CerebrasProvider does not implement chat_stream")
        yield  # pragma: no cover
