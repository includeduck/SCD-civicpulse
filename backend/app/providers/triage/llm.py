"""Hosted LLM triage via Groq's OpenAI-compatible chat completions API.

Requests JSON mode (``response_format: json_object``), then validates the
answer against TriageResult anyway (see prompt.py). Transport and status
errors become typed TriageErrors; retry and fallback live in TriageService.
"""

from __future__ import annotations

import httpx

from app.models.complaint import TriagedBy
from app.providers.triage._http import post_json
from app.providers.triage.base import TriageInvalidOutputError, TriageResult
from app.providers.triage.prompt import build_messages, parse_triage_json


class LLMTriage:
    name = TriagedBy.llm_groq.value

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.groq.com/openai/v1",
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("LLMTriage requires an API key")
        self.model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_seconds))

    def __repr__(self) -> str:  # never include the key
        return f"LLMTriage(model={self.model!r})"

    def triage(self, text: str, location: str) -> TriageResult:
        body = post_json(
            self._client,
            self._url,
            {
                "model": self.model,
                "messages": build_messages(text, location),
                "response_format": {"type": "json_object"},
                "temperature": 0,
                "max_tokens": 200,
            },
            provider=self.name,
            headers=self._headers,
        )
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TriageInvalidOutputError(f"{self.name}: no message content") from exc
        return parse_triage_json(content, self.name)

    def close(self) -> None:
        self._client.close()
