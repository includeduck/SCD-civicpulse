"""Offline triage via a local Ollama container (no key, no PII leaves the host).

Uses ``/api/chat`` with ``format`` set to the TriageResult JSON schema, so the
model is constrained to the enums; the answer is still validated in prompt.py.
"""

from __future__ import annotations

import httpx

from app.models.complaint import TriagedBy
from app.providers.triage._http import post_json
from app.providers.triage.base import TriageInvalidOutputError, TriageResult
from app.providers.triage.prompt import OUTPUT_SCHEMA, build_messages, parse_triage_json


class OllamaTriage:
    name = TriagedBy.llm_ollama.value

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self._url = f"{base_url.rstrip('/')}/api/chat"
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_seconds))

    def triage(self, text: str, location: str) -> TriageResult:
        body = post_json(
            self._client,
            self._url,
            {
                "model": self.model,
                "messages": build_messages(text, location),
                "format": OUTPUT_SCHEMA,
                "stream": False,
                "options": {"temperature": 0},
            },
            provider=self.name,
        )
        try:
            content = body["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise TriageInvalidOutputError(f"{self.name}: no message content") from exc
        return parse_triage_json(content, self.name)

    def close(self) -> None:
        self._client.close()
