"""Async HTTP client for Ollama REST API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


class OllamaError(RuntimeError):
    """Raised when Ollama returns an error or is unreachable."""


class OllamaClient:
    """Thin async wrapper around the Ollama HTTP API."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> tuple[bool, dict[str, Any]]:
        try:
            resp = await self._client.get("/api/version")
            if resp.status_code == 200:
                return True, resp.json()
            return False, {"status_code": resp.status_code}
        except httpx.HTTPError as exc:
            return False, {"error": str(exc)}

    async def list_models(self) -> list[dict[str, Any]]:
        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return list(data.get("models", []))
        except httpx.HTTPError as exc:
            raise OllamaError(f"Failed to list models from Ollama: {exc}") from exc

    async def show_model(self, name: str) -> dict[str, Any]:
        try:
            resp = await self._client.post("/api/show", json={"name": name})
            resp.raise_for_status()
            return dict(resp.json())
        except httpx.HTTPError as exc:
            raise OllamaError(f"Failed to inspect model '{name}': {exc}") from exc

    async def pull_model(self, name: str) -> dict[str, Any]:
        try:
            resp = await self._client.post("/api/pull", json={"name": name, "stream": False})
            resp.raise_for_status()
            return dict(resp.json())
        except httpx.HTTPError as exc:
            raise OllamaError(f"Failed to pull model '{name}': {exc}") from exc

    async def delete_model(self, name: str) -> None:
        try:
            resp = await self._client.request("DELETE", "/api/delete", json={"name": name})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Failed to delete model '{name}': {exc}") from exc

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if options:
            payload["options"] = options
        try:
            resp = await self._client.post("/api/chat", json=payload)
            resp.raise_for_status()
            return dict(resp.json())
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama chat failed: {exc}") from exc

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if options:
            payload["options"] = options
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    yield json.loads(line)
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama streaming chat failed: {exc}") from exc
