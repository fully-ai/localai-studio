"""FastAPI application factory and REST/SSE endpoints for LocalAI Studio."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from localai_studio.config import Settings
from localai_studio.db import Database
from localai_studio.files import FileValidationError, load_image_base64, store_upload
from localai_studio.ollama_client import OllamaClient, OllamaError
from localai_studio.schemas import (
    ChatMessageRequest,
    ConversationCreate,
    ConversationUpdate,
    HealthResponse,
    ModelPullRequest,
    PreferencesUpdate,
    SystemPromptCreate,
)

logger = logging.getLogger("localai_studio")
STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    settings: Settings | None = None,
    ollama_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    cfg = settings or Settings()
    cfg.ensure_directories()

    db = Database(cfg.db_path)
    ollama = OllamaClient(
        base_url=cfg.ollama_base_url,
        timeout=cfg.ollama_timeout_seconds,
        transport=ollama_transport,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await db.connect()
        try:
            yield
        finally:
            await ollama.close()
            await db.close()

    app = FastAPI(
        title="LocalAI Studio",
        version="0.1.0",
        description="Self-hosted web workspace and API for local Ollama AI models.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    app.state.settings = cfg
    app.state.db = db
    app.state.ollama = ollama

    @app.exception_handler(OllamaError)
    async def handle_ollama_error(_request: Request, exc: OllamaError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        reachable, details = await ollama.health()
        return HealthResponse(
            status="ok",
            ollama_reachable=reachable,
            ollama_url=cfg.ollama_base_url,
            details=details,
        )

    # --- Models ---
    @app.get("/api/models")
    async def list_models() -> dict[str, Any]:
        models = await ollama.list_models()
        return {"models": models}

    @app.post("/api/models/pull")
    async def pull_model(req: ModelPullRequest) -> dict[str, Any]:
        result = await ollama.pull_model(req.name)
        return {"status": "pulled", "model": req.name, "details": result}

    @app.get("/api/models/{name:path}")
    async def show_model(name: str) -> dict[str, Any]:
        return await ollama.show_model(name)

    @app.delete("/api/models/{name:path}")
    async def delete_model(name: str) -> dict[str, str]:
        await ollama.delete_model(name)
        return {"status": "deleted", "model": name}

    # --- Conversations ---
    @app.get("/api/conversations")
    async def list_conversations() -> dict[str, Any]:
        items = await db.list_conversations()
        return {"conversations": items}

    @app.post("/api/conversations", status_code=201)
    async def create_conversation(req: ConversationCreate) -> dict[str, Any]:
        return await db.create_conversation(
            title=req.title,
            model=req.model,
            system_prompt=req.system_prompt,
            parameters=req.parameters.model_dump(),
        )

    @app.get("/api/conversations/{conv_id}")
    async def get_conversation(conv_id: str) -> dict[str, Any]:
        conv = await db.get_conversation(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        messages = await db.list_messages(conv_id)
        return {**conv, "messages": messages}

    @app.patch("/api/conversations/{conv_id}")
    async def update_conversation(conv_id: str, req: ConversationUpdate) -> dict[str, Any]:
        updated = await db.update_conversation(
            conv_id,
            title=req.title,
            model=req.model,
            system_prompt=req.system_prompt,
            parameters=req.parameters.model_dump() if req.parameters is not None else None,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return updated

    @app.delete("/api/conversations/{conv_id}")
    async def delete_conversation(conv_id: str) -> dict[str, str]:
        deleted = await db.delete_conversation(conv_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"status": "deleted"}

    # --- Files ---
    @app.post("/api/files", status_code=201)
    async def upload_file(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
        content = await file.read(cfg.max_upload_bytes + 1)
        if len(content) > cfg.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum size of {cfg.max_upload_bytes} bytes.",
            )
        try:
            stored = store_upload(
                upload_dir=cfg.upload_dir,
                raw_filename=file.filename or "upload",
                content=content,
                max_bytes=cfg.max_upload_bytes,
            )
        except FileValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        record = await db.create_attachment(
            attachment_id=stored.attachment_id,
            filename=stored.filename,
            stored_name=stored.stored_name,
            mime_type=stored.mime_type,
            kind=stored.kind,
            size_bytes=stored.size_bytes,
            extracted_text=stored.extracted_text,
        )
        return record

    # --- Chat ---
    async def _build_ollama_messages(conv: dict[str, Any]) -> list[dict[str, Any]]:
        history = await db.list_messages(conv["id"])
        ollama_msgs: list[dict[str, Any]] = []
        if conv["system_prompt"].strip():
            ollama_msgs.append({"role": "system", "content": conv["system_prompt"]})

        for msg in history:
            text_parts = [msg["content"]]
            images: list[str] = []
            for att_id in msg.get("attachment_ids", []):
                att = await db.get_attachment(att_id)
                if att is None:
                    continue
                if att["kind"] == "image":
                    images.append(load_image_base64(cfg.upload_dir, att["stored_name"]))
                elif att["kind"] == "text" and att["extracted_text"]:
                    text_parts.append(
                        f"\n\n[Attached file: {att['filename']}]\n```\n{att['extracted_text']}\n```"
                    )
            entry: dict[str, Any] = {
                "role": msg["role"],
                "content": "".join(text_parts),
            }
            if images:
                entry["images"] = images
            ollama_msgs.append(entry)
        return ollama_msgs

    @app.post("/api/conversations/{conv_id}/messages")
    async def send_message(conv_id: str, req: ChatMessageRequest):
        conv = await db.get_conversation(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        for att_id in req.attachment_ids:
            if await db.get_attachment(att_id) is None:
                raise HTTPException(status_code=400, detail=f"Unknown attachment id: {att_id}")

        user_msg = await db.add_message(conv_id, "user", req.content, req.attachment_ids)
        ollama_messages = await _build_ollama_messages(conv)
        options = conv["parameters"]

        if not req.stream:
            reply = await ollama.chat(model=conv["model"], messages=ollama_messages, options=options)
            assistant_text = reply.get("message", {}).get("content", "")
            assistant_msg = await db.add_message(conv_id, "assistant", assistant_text)
            return {"user_message": user_msg, "assistant_message": assistant_msg}

        async def sse_generator() -> AsyncIterator[str]:
            accumulated: list[str] = []
            yield f"data: {json.dumps({'type': 'user_message', 'message': user_msg})}\n\n"
            try:
                async for chunk in ollama.chat_stream(
                    model=conv["model"],
                    messages=ollama_messages,
                    options=options,
                ):
                    delta = chunk.get("message", {}).get("content", "")
                    if delta:
                        accumulated.append(delta)
                        yield f"data: {json.dumps({'type': 'delta', 'content': delta})}\n\n"
                    if chunk.get("done"):
                        full_text = "".join(accumulated)
                        assistant_msg = await db.add_message(conv_id, "assistant", full_text)
                        done_payload = {"type": "done", "message": assistant_msg}
                        yield f"data: {json.dumps(done_payload)}\n\n"
            except OllamaError as exc:
                yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    # --- System Prompts & Preferences ---
    @app.get("/api/prompts")
    async def list_prompts() -> dict[str, Any]:
        return {"prompts": await db.list_system_prompts()}

    @app.post("/api/prompts", status_code=201)
    async def create_prompt(req: SystemPromptCreate) -> dict[str, Any]:
        try:
            return await db.create_system_prompt(req.name, req.content)
        except Exception as exc:
            raise HTTPException(status_code=409, detail="Prompt name already exists") from exc

    @app.delete("/api/prompts/{prompt_id}")
    async def delete_prompt(prompt_id: str) -> dict[str, str]:
        if not await db.delete_system_prompt(prompt_id):
            raise HTTPException(status_code=404, detail="Prompt not found")
        return {"status": "deleted"}

    @app.get("/api/preferences")
    async def get_preferences() -> dict[str, Any]:
        return await db.get_preferences(cfg.default_model)

    @app.patch("/api/preferences")
    async def update_preferences(req: PreferencesUpdate) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if req.default_model is not None:
            updates["default_model"] = req.default_model
        if req.theme is not None:
            updates["theme"] = req.theme
        if req.stream_responses is not None:
            updates["stream_responses"] = req.stream_responses
        if req.default_parameters is not None:
            updates["default_parameters"] = req.default_parameters.model_dump()
        return await db.update_preferences(updates, cfg.default_model)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
