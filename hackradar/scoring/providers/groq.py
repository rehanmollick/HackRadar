"""Groq provider — Pass 1 triage using Llama 3.1 8B Instant.

Groq's free tier is ~30 RPM and 14,400 RPD on Llama 3.1 8B. Scan uses
~25 batch calls so we're well under limits. Very fast inference (~1s per call)
makes this the right fit for the cheap triage pass.
"""

from __future__ import annotations

from typing import AsyncIterator, Type, TypeVar

from pydantic import BaseModel

from hackradar import config
from hackradar.models import Item
from hackradar.scoring.providers._openai_compat import call_chat_json
from hackradar.scoring.providers.base import ProviderError

T = TypeVar("T", bound=BaseModel)

BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider:
    name = "groq"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or config.PASS1_MODEL
        self.api_key = api_key or config.GROQ_API_KEY

    async def call_batch(
        self,
        items: list[Item],
        prompt: str,
        response_schema: Type[T],
    ) -> T:
        if not self.api_key:
            raise ProviderError("GROQ_API_KEY is not set")
        return await call_chat_json(
            base_url=BASE_URL,
            api_key=self.api_key,
            model=self.model,
            prompt=prompt,
            response_schema=response_schema,
        )

    async def chat_stream(self, messages: list[dict], system: str) -> AsyncIterator[str]:
        raise NotImplementedError("GroqProvider does not implement chat_stream")
        yield  # pragma: no cover — make mypy happy about AsyncIterator
