"""resilient.py — the single source of truth for retry + fallback policy.

Providers stay dumb (single API call, raise on failure). This coordinator:

  1. Tries each provider in order.
  2. Retries a provider ONCE on TransientError.
  3. Skips the retry on RateLimitError (next provider instead — retrying
     a rate-limited provider will just re-trip).
  4. On ContextOverflowError or SchemaValidationError, falls through to
     the next provider immediately.
  5. If the last provider's batch call fails, splits the batch to
     individual calls against that same provider.
  6. Returns the items that successfully scored. Items that failed every
     attempt are silently omitted (with a warning log).
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, TypeVar

from pydantic import BaseModel

from hackradar.models import Item
from hackradar.scoring.providers.base import (
    ContextOverflowError,
    LLMProvider,
    ProviderError,
    RateLimitError,
    SchemaValidationError,
    TransientError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# A builder that takes a list of items and produces the prompt string for them.
# This allows the coordinator to rebuild prompts when splitting a failed batch.
PromptBuilder = Callable[[list[Item]], str]


async def call_with_fallback(
    providers: list[LLMProvider],
    items: list[Item],
    prompt_builder: PromptBuilder,
    response_schema: type[T],
) -> tuple[T | None, str | None]:
    """Try providers in order with retry + split-on-failure.

    Returns (parsed_response, provider_name_that_succeeded) on success,
    or (None, None) if every provider + individual split failed.

    Note: the return type is the full batch response, not the individual
    items. Callers zip the response back to items themselves.
    """
    if not items:
        return None, None

    prompt = prompt_builder(items)
    last_exc: Exception | None = None

    for idx, provider in enumerate(providers):
        is_last = idx == len(providers) - 1
        try:
            result = await _try_provider_with_retry(provider, items, prompt, response_schema)
            return result, provider.name
        except RateLimitError as exc:
            logger.warning("[%s] rate limited, falling through: %s", provider.name, exc)
            last_exc = exc
            continue
        except ContextOverflowError as exc:
            logger.warning("[%s] context overflow, falling through: %s", provider.name, exc)
            last_exc = exc
            continue
        except SchemaValidationError as exc:
            logger.warning("[%s] schema validation failed, falling through: %s", provider.name, exc)
            last_exc = exc
            continue
        except ProviderError as exc:
            logger.warning("[%s] provider error, falling through: %s", provider.name, exc)
            last_exc = exc
            if is_last:
                # On the last provider, try splitting the batch before giving up.
                split_result = await _split_and_retry(
                    provider, items, prompt_builder, response_schema
                )
                if split_result is not None:
                    return split_result, provider.name
            continue

    logger.error(
        "All providers failed for batch of %d items. Last error: %s",
        len(items),
        last_exc,
    )
    return None, None


async def _try_provider_with_retry(
    provider: LLMProvider,
    items: list[Item],
    prompt: str,
    response_schema: type[T],
) -> T:
    """Call a provider, retrying ONCE on TransientError. RateLimit skips retry."""
    try:
        return await provider.call_batch(items, prompt, response_schema)
    except TransientError as exc:
        logger.warning("[%s] transient error, retrying once: %s", provider.name, exc)
        return await provider.call_batch(items, prompt, response_schema)


async def _split_and_retry(
    provider: LLMProvider,
    items: list[Item],
    prompt_builder: PromptBuilder,
    response_schema: type[T],
) -> T | None:
    """Last-ditch: call the provider once per item and merge successes.

    Returns a schema instance with the `items` attribute populated with
    the successful individual responses, or None if every call failed.
    """
    if len(items) == 1:
        return None  # Already individual, nothing to split.

    individual_results: list[Any] = []
    for item in items:
        single_prompt = prompt_builder([item])
        try:
            result = await provider.call_batch([item], single_prompt, response_schema)
            if hasattr(result, "items"):
                individual_results.extend(result.items)
            else:
                individual_results.append(result)
        except ProviderError as exc:
            logger.warning(
                "[%s] individual call failed for %r: %s", provider.name, item.title, exc
            )

    if not individual_results:
        return None

    # Reconstruct the batch response shape.
    return response_schema.model_validate({"items": individual_results})
