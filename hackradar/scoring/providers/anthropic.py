"""Anthropic Claude provider for Pass 3 — interactive deep-dive chat.

This is the only provider that implements chat_stream(). It does NOT implement
call_batch — Pass 3 is conversational, not structured-JSON. Calling call_batch
on this provider raises NotImplementedError so a Pass 1/2 misconfiguration
fails fast instead of going to the wrong model.

Streaming uses Anthropic's SDK with `client.messages.stream(...)` so we can
yield individual text deltas to the FastAPI SSE endpoint.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from hackradar import config
from hackradar.scoring.providers.base import (
    ProviderError,
    RateLimitError,
    TransientError,
)

logger = logging.getLogger(__name__)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or config.PASS3_MODEL
        self._api_key = api_key or config.ANTHROPIC_API_KEY

    async def call_batch(self, items, prompt, response_schema):
        raise NotImplementedError(
            "AnthropicProvider is Pass 3 only — call chat_stream(), not call_batch()."
        )

    async def chat_stream(
        self,
        messages: list[dict],
        system: str,
    ) -> AsyncIterator[str]:
        """Stream Anthropic message deltas as plain text chunks.

        `messages` follows the Anthropic format: [{"role": "user"|"assistant",
        "content": str}, ...]. `system` is the system prompt.
        """
        if not self._api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")

        try:
            from anthropic import AsyncAnthropic
            from anthropic import APIStatusError, APIConnectionError, RateLimitError as _RL
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(f"anthropic package not installed: {exc}")

        client = AsyncAnthropic(api_key=self._api_key)
        try:
            async with client.messages.stream(
                model=self.model,
                max_tokens=2048,
                system=system,
                messages=messages,
            ) as stream:
                async for chunk in stream.text_stream:
                    if chunk:
                        yield chunk
        except _RL as exc:
            raise RateLimitError(f"anthropic 429: {exc}") from exc
        except APIConnectionError as exc:
            raise TransientError(f"anthropic connection error: {exc}") from exc
        except APIStatusError as exc:
            status = getattr(exc, "status_code", None)
            if status and status >= 500:
                raise TransientError(f"anthropic {status}: {exc}") from exc
            raise ProviderError(f"anthropic {status}: {exc}") from exc
