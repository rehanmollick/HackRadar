"""Shared helper for OpenAI-compatible chat completions endpoints.

Groq and Cerebras both expose an OpenAI-compatible /chat/completions API
with JSON mode support. This helper handles the HTTP call, error mapping,
and schema validation so each provider is a thin config wrapper.
"""

from __future__ import annotations

import json
from typing import Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from hackradar.scoring.providers.base import (
    ProviderError,
    RateLimitError,
    SchemaValidationError,
    TransientError,
)

T = TypeVar("T", bound=BaseModel)


async def call_chat_json(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    response_schema: Type[T],
    timeout_s: float = 60.0,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    extra_headers: dict[str, str] | None = None,
) -> T:
    """POST to an OpenAI-compatible /chat/completions with JSON response_format.

    Returns a parsed instance of response_schema. Raises our provider errors
    on any upstream failure.

    extra_headers: optional extra HTTP headers merged into the request.
        OpenRouter needs HTTP-Referer + X-Title for free-tier attribution.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise TransientError(f"{model}: timeout after {timeout_s}s") from exc
    except httpx.TransportError as exc:
        raise TransientError(f"{model}: transport error: {exc}") from exc

    if response.status_code == 429:
        raise RateLimitError(f"{model}: 429 rate limited ({response.text[:200]})")
    if response.status_code >= 500:
        raise TransientError(
            f"{model}: {response.status_code} {response.text[:200]}"
        )
    if response.status_code >= 400:
        raise ProviderError(
            f"{model}: {response.status_code} {response.text[:500]}"
        )

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise ProviderError(f"{model}: response not JSON: {response.text[:200]}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"{model}: unexpected response shape: {data}") from exc

    # Free OpenRouter models occasionally return content=None when their
    # upstream rejects the prompt (content filter, no provider available,
    # finish_reason='error', etc). Treat that as a recoverable provider
    # error so the resilient layer falls through to the next provider
    # instead of crashing the whole scan with TypeError.
    if content is None:
        finish_reason = (
            data.get("choices", [{}])[0].get("finish_reason")
            if isinstance(data, dict)
            else None
        )
        raise ProviderError(
            f"{model}: response content is None "
            f"(finish_reason={finish_reason!r}, raw={str(data)[:300]})"
        )
    if not isinstance(content, str):
        raise ProviderError(
            f"{model}: response content has unexpected type {type(content).__name__}"
        )

    try:
        parsed_json = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(
            f"{model}: content is not valid JSON: {content[:300]}"
        ) from exc

    try:
        return response_schema.model_validate(parsed_json)
    except ValidationError as exc:
        raise SchemaValidationError(
            f"{model}: JSON does not match {response_schema.__name__}: {exc}"
        ) from exc
