"""Integration tests for LocalAI Studio FastAPI endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from localai_studio.app import create_app
from localai_studio.config import Settings

VALID_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"


def _make_mock_ollama_transport(captured_payloads: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.5.1"})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [{"name": "llama3.2:latest", "size": 2_000_000_000}]},
            )
        if request.url.path == "/api/pull":
            return httpx.Response(200, json={"status": "success"})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"modelfile": "FROM llama3.2"})
        if request.url.path == "/api/delete":
            return httpx.Response(200, json={"status": "deleted"})
        if request.url.path == "/api/chat":
            payload = json.loads(request.content.decode("utf-8"))
            captured_payloads.append(payload)
            if payload.get("stream"):
                lines = [
                    json.dumps({"message": {"role": "assistant", "content": "Hello "}, "done": False}),
                    json.dumps({"message": {"role": "assistant", "content": "world!"}, "done": True}),
                ]
                body = ("\n".join(lines) + "\n").encode("utf-8")
                return httpx.Response(200, content=body, headers={"content-type": "application/x-ndjson"})
            return httpx.Response(
                200,
                json={"message": {"role": "assistant", "content": "Sync reply"}, "done": True},
            )
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.fixture()
def client(tmp_path: Path) -> tuple[TestClient, list[dict]]:
    captured: list[dict] = []
    settings = Settings(data_dir=tmp_path / "data", max_upload_bytes=1024 * 1024)
    app = create_app(settings=settings, ollama_transport=_make_mock_ollama_transport(captured))
    with TestClient(app) as test_client:
        yield test_client, captured


def test_health_and_models(client: tuple[TestClient, list[dict]]) -> None:
    tc, _ = client
    res = tc.get("/api/health")
    assert res.status_code == 200
    assert res.json()["ollama_reachable"] is True

    models = tc.get("/api/models").json()["models"]
    assert models[0]["name"] == "llama3.2:latest"

    pull = tc.post("/api/models/pull", json={"name": "mistral:7b"})
    assert pull.status_code == 200

    show = tc.get("/api/models/llama3.2:latest")
    assert show.status_code == 200


def test_conversation_crud_and_chat_streaming(client: tuple[TestClient, list[dict]]) -> None:
    tc, captured = client

    created = tc.post(
        "/api/conversations",
        json={"title": "Architecture Review", "model": "llama3.2:latest", "system_prompt": "Be concise."},
    )
    assert created.status_code == 201
    conv_id = created.json()["id"]

    # Upload text and image attachments
    txt_res = tc.post("/api/files", files={"file": ("spec.txt", b"Service runs on port 8080", "text/plain")})
    assert txt_res.status_code == 201
    txt_id = txt_res.json()["id"]

    img_res = tc.post("/api/files", files={"file": ("arch.png", VALID_PNG, "image/png")})
    assert img_res.status_code == 201
    img_id = img_res.json()["id"]

    # Streaming chat with attachments
    with tc.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Summarize this", "attachment_ids": [txt_id, img_id], "stream": True},
    ) as stream_res:
        assert stream_res.status_code == 200
        events = [
            json.loads(line[6:])
            for line in stream_res.iter_lines()
            if line.startswith("data: ")
        ]

    deltas = [e["content"] for e in events if e["type"] == "delta"]
    assert "".join(deltas) == "Hello world!"
    assert any(e["type"] == "done" for e in events)

    # Verify Ollama received system prompt, extracted text, and base64 image
    sent = captured[-1]
    assert sent["messages"][0] == {"role": "system", "content": "Be concise."}
    assert "Service runs on port 8080" in sent["messages"][1]["content"]
    assert len(sent["messages"][1]["images"]) == 1

    # Verify history persisted
    conv_detail = tc.get(f"/api/conversations/{conv_id}").json()
    assert len(conv_detail["messages"]) == 2
    assert conv_detail["messages"][1]["content"] == "Hello world!"

    # Update & delete
    upd = tc.patch(f"/api/conversations/{conv_id}", json={"title": "Renamed"})
    assert upd.status_code == 200
    assert upd.json()["title"] == "Renamed"

    assert tc.delete(f"/api/conversations/{conv_id}").status_code == 200
    assert tc.get(f"/api/conversations/{conv_id}").status_code == 404


def test_prompts_and_preferences(client: tuple[TestClient, list[dict]]) -> None:
    tc, _ = client
    p = tc.post("/api/prompts", json={"name": "Code Reviewer", "content": "Review for security."})
    assert p.status_code == 201
    prompt_id = p.json()["id"]
    assert len(tc.get("/api/prompts").json()["prompts"]) == 1
    assert tc.delete(f"/api/prompts/{prompt_id}").status_code == 200

    prefs = tc.patch("/api/preferences", json={"theme": "light", "default_model": "qwen2.5:7b"})
    assert prefs.status_code == 200
    assert prefs.json()["theme"] == "light"
    assert prefs.json()["default_model"] == "qwen2.5:7b"
