from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx


class ProviderError(RuntimeError):
    def __init__(self, message: str, stream_diagnostics=None):
        self.stream_diagnostics = stream_diagnostics or []
        if self.stream_diagnostics:
            message += "\nStream diagnostics: " + json.dumps(self.stream_diagnostics)
        super().__init__(message)


class ProviderCancelled(ProviderError):
    """The provider acknowledged cancellation of an in-flight request."""

    def __init__(self, message: str, request_id: str = "", stream_diagnostics=None):
        self.request_id = request_id
        super().__init__(message, stream_diagnostics)


@dataclass
class OpenAICompatibleProvider:
    base_url: str
    api_key: str
    model: str
    timeout: float = 120
    active_request_ids: set[str] = field(default_factory=set, init=False, repr=False)

    @staticmethod
    def _error_text(exc: Exception) -> str:
        message = str(exc).strip()
        return message or type(exc).__name__

    async def cancel_request(self, request_id: str) -> dict:
        """Ask Qwen-compatible gateways to cancel one active request.

        A 404 means the request already finished or was already cancelled and
        is therefore treated as a successful no-op. Other cancellation errors
        are returned as diagnostics so stopping a job never masks its state.
        """
        if not request_id:
            return {"status": "missing_request_id"}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        endpoint = self.base_url.rstrip("/") + "/requests/" + quote(request_id, safe="")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=20, write=20, pool=10)) as client:
                response = await client.delete(endpoint, headers=headers)
                if response.status_code == 404:
                    return {"request_id": request_id, "status": "not_found"}
                response.raise_for_status()
                try:
                    value = response.json()
                except ValueError:
                    value = {"request_id": request_id, "status": "cancellation_requested"}
                return value if isinstance(value, dict) else {"request_id": request_id, "status": "cancellation_requested"}
        except httpx.HTTPError as exc:
            return {"request_id": request_id, "status": "error", "error": self._error_text(exc)}

    async def cancel_active_requests(self) -> list[dict]:
        request_ids = list(self.active_request_ids)
        if not request_ids:
            return []
        return list(await asyncio.gather(*(self.cancel_request(request_id) for request_id in request_ids)))

    async def _complete_stream(self, prompt: str, max_attempts: int, on_token=None, request_options: dict | None = None) -> str:
        """Assemble an OpenAI-compatible SSE response without a generation timeout."""
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                   "temperature": 0.2, "stream": True}
        if request_options:
            allowed = {"web_search", "enable_thinking"}
            payload.update({key: value for key, value in request_options.items() if key in allowed})
        last = ""
        diagnostics = []
        timeout = httpx.Timeout(connect=20, read=None, write=60, pool=20)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(max_attempts):
                pieces: list[str] = []
                started = time.monotonic()
                active_request_id = ""
                info = {"attempt": attempt + 1, "keepalive_comments": 0,
                        "data_events": 0, "malformed_events": 0, "other_lines": 0,
                        "content_characters": 0, "reasoning_characters": 0,
                        "error_events": 0, "finish_reasons": [], "done_received": False}
                diagnostics.append(info)
                try:
                    async with client.stream("POST", self.base_url.rstrip("/") + "/chat/completions",
                                             headers=headers, json=payload) as response:
                        active_request_id = response.headers.get("x-qwen-request-id", "")
                        if active_request_id:
                            self.active_request_ids.add(active_request_id)
                            info["qwen_request_id"] = active_request_id
                        info["http_status"] = response.status_code
                        info["response_headers"] = {
                            name: value.replace(self.api_key, "[redacted]")[:200] if self.api_key else value[:200]
                            for name in ("content-type", "x-qwen-request-id", "x-qwen-grounding-mode",
                                         "x-qwen-web-search", "x-qwen-web-search-success",
                                         "x-qwen-search-policy", "x-qwen-search-category", "x-qwen-search-calls")
                            if (value := response.headers.get(name)) is not None
                        }
                        if response.status_code == 429:
                            retry = min(float(response.headers.get("retry-after", 2 ** attempt)), 60)
                            await response.aread()
                            await asyncio.sleep(retry)
                            last = "HTTP 429: provider rate limit"
                            continue
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if line.startswith(":"):
                                info["keepalive_comments"] += 1
                            elif line and not line.startswith("data:"):
                                info["other_lines"] += 1
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                info["done_received"] = True
                            if not data or data == "[DONE]":
                                continue
                            info["data_events"] += 1
                            try:
                                event = json.loads(data)
                                if isinstance(event, dict) and event.get("error"):
                                    # Never retain raw error bodies or private reasoning text.
                                    info["error_events"] += 1
                                    error = event.get("error")
                                    if isinstance(error, dict) and error.get("type") == "request_cancelled":
                                        raise ProviderCancelled(
                                            error.get("message") or "Provider request was cancelled",
                                            request_id=error.get("request_id") or active_request_id,
                                            stream_diagnostics=diagnostics,
                                        )
                                choices = event.get("choices") if isinstance(event, dict) else None
                                if choices and isinstance(choices[0], dict):
                                    reason = choices[0].get("finish_reason")
                                    if reason in ("stop", "length", "content_filter", "tool_calls", "function_call") and reason not in info["finish_reasons"]:
                                        info["finish_reasons"].append(reason)
                                delta = event.get("choices", [{}])[0].get("delta", {})
                                if isinstance(delta, dict):
                                    info["reasoning_characters"] += sum(len(delta.get(k) or "") for k in ("reasoning_content", "reasoning") if isinstance(delta.get(k), str))
                                token = delta.get("content")
                                if token:
                                    info["content_characters"] += len(token)
                                    info.setdefault("first_content_seconds", round(time.monotonic() - started, 2))
                                    pieces.append(token)
                                    if on_token:
                                        on_token(token)
                            except (json.JSONDecodeError, IndexError, AttributeError):
                                info["malformed_events"] += 1
                                # One malformed SSE event must not discard already received tokens.
                                continue
                    if pieces:
                        return "".join(pieces)
                    last = "Provider stream completed without content"
                except ProviderCancelled:
                    raise
                except httpx.HTTPError as exc:
                    last = self._error_text(exc)
                    info["transport_error"] = type(exc).__name__
                finally:
                    if active_request_id:
                        self.active_request_ids.discard(active_request_id)
                    info["elapsed_seconds"] = round(time.monotonic() - started, 2)
                if attempt + 1 < max_attempts:
                    await asyncio.sleep(min(2 ** attempt + random.random(), 20))
        raise ProviderError(last or "Provider stream did not return content", diagnostics)

    async def _complete(self, prompt: str, max_attempts: int, json_mode: bool) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        last = ""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(max_attempts):
                active_request_id = ""
                try:
                    async with client.stream("POST", self.base_url.rstrip("/") + "/chat/completions", headers=headers, json=payload) as response:
                        active_request_id = response.headers.get("x-qwen-request-id", "")
                        if active_request_id:
                            self.active_request_ids.add(active_request_id)
                        if response.status_code == 429:
                            retry = min(float(response.headers.get("retry-after", 2 ** attempt)), 60)
                            await response.aread()
                            await asyncio.sleep(retry)
                            continue
                        response.raise_for_status()
                        await response.aread()
                        body = response.json()
                        error = body.get("error") if isinstance(body, dict) else None
                        if isinstance(error, dict) and error.get("type") == "request_cancelled":
                            raise ProviderCancelled(
                                error.get("message") or "Provider request was cancelled",
                                request_id=error.get("request_id") or active_request_id,
                            )
                        return body["choices"][0]["message"]["content"]
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    last = self._error_text(exc)
                    if attempt + 1 < max_attempts:
                        await asyncio.sleep(min(2 ** attempt + random.random(), 20))
                finally:
                    if active_request_id:
                        self.active_request_ids.discard(active_request_id)
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
