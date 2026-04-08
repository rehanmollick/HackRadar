"""Base Protocol and errors for HackRadar V2 LLM providers.

Providers are intentionally dumb: they make the API call and raise on failure.
All retry and cross-provider fallback logic lives in hackradar.scoring.resilient.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, TypeVar

from pydantic import BaseModel

from hackradar.models import Item

T = TypeVar("T", bound=BaseModel)


class ProviderError(Exception):
    """Base class for provider-level failures."""


class RateLimitError(ProviderError):
    """Raised on 429 from upstream OR client-side rate-limit trip."""


class TransientError(ProviderError):
    """Network, 5xx, or timeout. The resilient coordinator will retry once."""


class ContextOverflowError(ProviderError):
    """Raised BEFORE making an API call when a batch would exceed the model's context.

    Critical: this MUST be raised client-side so we never waste an API call.
    """


class SchemaValidationError(ProviderError):
    """The provider returned text but it didn't parse into the requested Pydantic schema."""


class LLMProvider(Protocol):
    """Generic LLM provider interface used by all three scoring passes.

    Pass 1 calls call_batch with TriageBatchResponse schema.
    Pass 2 calls call_batch with ScoringBatchResponse schema.
    Pass 3 calls chat_stream (only implemented by the Anthropic provider).
    """

    name: str
    model: str

    async def call_batch(
        self,
        items: list[Item],
        prompt: str,
        response_schema: type[T],
    ) -> T:
        """Structured JSON batch call. Returns a parsed schema instance.

        Raises:
            ContextOverflowError: if the batch would exceed the model context budget.
            RateLimitError: on 429 from the API.
            TransientError: on 5xx, timeout, or connection error.
            SchemaValidationError: on JSON-parseable but schema-invalid response.
            ProviderError: for any other provider-side failure.
        """
        ...

    async def chat_stream(
        self,
        messages: list[dict],
        system: str,
    ) -> AsyncIterator[str]:
        """SSE-friendly streaming chat. Pass 3 only. Yields text chunks."""
        ...
