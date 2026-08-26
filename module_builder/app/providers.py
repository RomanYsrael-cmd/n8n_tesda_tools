from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass

import httpx


class ProviderError(RuntimeError):
    pass


@dataclass
class OpenAICompatibleProvider:
    base_url: str
    api_key: str
    model: str
    timeout: float = 120

    async def complete_json(self, prompt: str, max_attempts: int = 4) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}, "temperature": 0.2}
        last = ""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(max_attempts):
                try:
                    response = await client.post(self.base_url.rstrip("/") + "/chat/completions", headers=headers, json=payload)
                    if response.status_code == 429:
                        retry = min(float(response.headers.get("retry-after", 2 ** attempt)), 60)
                        await asyncio.sleep(retry)
                        continue
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
                    return json.loads(strip_markdown_fences(content))
                except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
                    last = str(exc)
                    if attempt + 1 < max_attempts:
                        await asyncio.sleep(min(2 ** attempt + random.random(), 20))
        raise ProviderError(last or "Provider did not return valid JSON")

    async def test(self) -> tuple[bool, str]:
        try:
            result = await self.complete_json('Return only {"ok": true}.', max_attempts=1)
            return bool(result.get("ok")), "Connection succeeded" if result.get("ok") else "Provider responded, but JSON was unexpected"
        except Exception as exc:
            return False, str(exc)


def strip_markdown_fences(value: str) -> str:
    text = value.strip().lstrip("\ufeff")
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()

