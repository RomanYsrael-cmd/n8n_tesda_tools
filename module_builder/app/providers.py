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

    @staticmethod
    def _error_text(exc: Exception) -> str:
        message = str(exc).strip()
        return message or type(exc).__name__

    async def _complete_stream(self, prompt: str, max_attempts: int, on_token=None, request_options: dict | None = None) -> str:
        """Assemble an OpenAI-compatible SSE response without a generation timeout."""
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                   "temperature": 0.2, "stream": True}
        if request_options:
            allowed = {"web_search", "enable_thinking"}
            payload.update({key: value for key, value in request_options.items() if key in allowed})
        last = ""
        timeout = httpx.Timeout(connect=20, read=None, write=60, pool=20)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(max_attempts):
                pieces: list[str] = []
                try:
                    async with client.stream("POST", self.base_url.rstrip("/") + "/chat/completions",
                                             headers=headers, json=payload) as response:
                        if response.status_code == 429:
                            retry = min(float(response.headers.get("retry-after", 2 ** attempt)), 60)
                            await response.aread()
                            await asyncio.sleep(retry)
                            last = "HTTP 429: provider rate limit"
                            continue
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if not data or data == "[DONE]":
                                continue
                            try:
                                event = json.loads(data)
                                delta = event.get("choices", [{}])[0].get("delta", {})
                                token = delta.get("content")
                                if token:
                                    pieces.append(token)
                                    if on_token:
                                        on_token(token)
                            except (json.JSONDecodeError, IndexError, AttributeError):
                                # One malformed SSE event must not discard already received tokens.
                                continue
                    if pieces:
                        return "".join(pieces)
                    last = "Provider stream completed without content"
                except httpx.HTTPError as exc:
                    last = self._error_text(exc)
                if attempt + 1 < max_attempts:
                    await asyncio.sleep(min(2 ** attempt + random.random(), 20))
        raise ProviderError(last or "Provider stream did not return content")

    async def _complete(self, prompt: str, max_attempts: int, json_mode: bool) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
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
                    return response.json()["choices"][0]["message"]["content"]
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    last = self._error_text(exc)
                    if attempt + 1 < max_attempts:
                        await asyncio.sleep(min(2 ** attempt + random.random(), 20))
        raise ProviderError(last or "Provider did not return valid JSON")

    async def complete_text(self, prompt: str, max_attempts: int = 4, on_token=None, request_options: dict | None = None) -> str:
        return (await self._complete_stream(prompt, max_attempts, on_token=on_token, request_options=request_options)).strip()

    async def complete_json(self, prompt: str, max_attempts: int = 4) -> dict:
        content = await self._complete(prompt, max_attempts, json_mode=True)
        try:
            return json.loads(strip_markdown_fences(content))
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Provider returned invalid JSON: {exc}") from exc

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
