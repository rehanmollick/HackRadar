"""Cerebras provider — fast inference for Pass 1 triage AND Pass 2 scoring.

Cerebras free-tier limits (per model, as of 2026-04-08):
  llama3.1-8b                  : 30 RPM, 60K TPM, 1M TPD, 8K  context
  qwen-3-235b-a22b-instruct-2507: 30 RPM, 30K TPM, 1M TPD, 64K context

llama3.1-8b is what we use for Pass 1 because its 60K TPM gives us
10x the throughput Groq offers on the same model (Groq free is 6K TPM).

qwen-3-235b is Pass 2. Its huge 64K context lets us batch many more
items per call than the old 8K-window qwen-3-32b we were using, but
the 30K TPM ceiling still dictates how often we can fire batches.

We enforce the context ceiling CLIENT-SIDE before calling the API so
an oversized batch raises ContextOverflowError instead of burning a
round-trip.
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

# Per-model context budgets (hard ceiling, leaving room for response).
# These match the "Max Context Length" Cerebras advertises on their
# Limits page, minus a safety margin for response tokens.
_CONTEXT_BUDGETS: dict[str, int] = {
    "llama3.1-8b": 7500,                          # 8192 ctx - response reserve
    "qwen-3-235b-a22b-instruct-2507": 60000,      # 65536 ctx - response reserve
    "gpt-oss-120b": 60000,
    "zai-glm-4.7": 60000,
}

# Default ceiling if the model isn't in the table (safest small value).
_DEFAULT_CONTEXT_BUDGET = 7500


def _budget_for(model: str) -> int:
    return _CONTEXT_BUDGETS.get(model, _DEFAULT_CONTEXT_BUDGET)


class CerebrasProvider:
    """Cerebras-hosted OpenAI-compatible chat/completions provider.

    Usage:
        # Pass 1 triage (fast, small model)
        CerebrasProvider(model="llama3.1-8b", name="cerebras_llama8b")

        # Pass 2 scoring (quality, big model)
        CerebrasProvider(model="qwen-3-235b-a22b-instruct-2507", name="cerebras_qwen235b")

    If model is None, falls back to config.PASS2_MODEL for backward compat.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        context_budget: int | None = None,
        name: str | None = None,
    ):
        self.model = model or config.PASS2_MODEL
        self.api_key = api_key or config.CEREBRAS_API_KEY
        self.context_budget = context_budget or _budget_for(self.model)
        # Different provider names let the coordinator log which Cerebras
        # instance failed (llama vs qwen) instead of a generic "cerebras".
        self.name = name or f"cerebras_{self.model.split('-')[0]}"

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
        if total > self.context_budget:
            raise ContextOverflowError(
                f"{self.model}: batch of {len(items)} items estimated at "
                f"{total} tokens (prompt={prompt_tokens}, reserve={response_reserve}) "
                f"exceeds context budget {self.context_budget}"
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
