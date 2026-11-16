"""Async SQLite persistence layer for conversations, messages, files, and preferences."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    model TEXT NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT '',
    parameters_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant')),
    content TEXT NOT NULL,
    attachment_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conv_created
    ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('image', 'text')),
    size_bytes INTEGER NOT NULL,
    extracted_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_prompts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class Database:
    """Async SQLite repository."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database connection is not initialized")
        return self._conn

    async def create_conversation(
        self,
        title: str,
        model: str,
        system_prompt: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        conv_id = uuid.uuid4().hex
        now = utcnow_iso()
        await self.conn.execute(
            """
            INSERT INTO conversations (id, title, model, system_prompt, parameters_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (conv_id, title, model, system_prompt, json.dumps(parameters), now, now),
        )
        await self.conn.commit()
        return await self.get_conversation(conv_id)  # type: ignore[return-value]

    async def list_conversations(self) -> list[dict[str, Any]]:
        cursor = await self.conn.execute(
            """
            SELECT id, title, model, system_prompt, parameters_json, created_at, updated_at
            FROM conversations
            ORDER BY updated_at DESC
            """
        )
        rows = await cursor.fetchall()
        return [self._row_to_conversation(r) for r in rows]

    async def get_conversation(self, conv_id: str) -> dict[str, Any] | None:
        cursor = await self.conn.execute(
            """
            SELECT id, title, model, system_prompt, parameters_json, created_at, updated_at
            FROM conversations WHERE id = ?
            """,
            (conv_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_conversation(row)

    async def update_conversation(
        self,
        conv_id: str,
        title: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        existing = await self.get_conversation(conv_id)
        if existing is None:
            return None
        new_title = title if title is not None else existing["title"]
        new_model = model if model is not None else existing["model"]
        new_prompt = system_prompt if system_prompt is not None else existing["system_prompt"]
        new_params = parameters if parameters is not None else existing["parameters"]
        now = utcnow_iso()
        await self.conn.execute(
            """
            UPDATE conversations
            SET title = ?, model = ?, system_prompt = ?, parameters_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_title, new_model, new_prompt, json.dumps(new_params), now, conv_id),
        )
        await self.conn.commit()
        return await self.get_conversation(conv_id)

    async def delete_conversation(self, conv_id: str) -> bool:
        cursor = await self.conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        attachment_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        msg_id = uuid.uuid4().hex
        now = utcnow_iso()
        att_ids = attachment_ids or []
        await self.conn.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, attachment_ids_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (msg_id, conversation_id, role, content, json.dumps(att_ids), now),
        )
        await self.conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        await self.conn.commit()
        return {
            "id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "attachment_ids": att_ids,
            "created_at": now,
        }

    async def list_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        cursor = await self.conn.execute(
            """
            SELECT id, conversation_id, role, content, attachment_ids_json, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "conversation_id": r["conversation_id"],
                "role": r["role"],
                "content": r["content"],
                "attachment_ids": json.loads(r["attachment_ids_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    async def create_attachment(
        self,
        attachment_id: str,
        filename: str,
        stored_name: str,
        mime_type: str,
        kind: str,
        size_bytes: int,
        extracted_text: str,
    ) -> dict[str, Any]:
        now = utcnow_iso()
        await self.conn.execute(
            """
            INSERT INTO attachments (id, filename, stored_name, mime_type, kind, size_bytes, extracted_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (attachment_id, filename, stored_name, mime_type, kind, size_bytes, extracted_text, now),
        )
        await self.conn.commit()
        return {
            "id": attachment_id,
            "filename": filename,
            "stored_name": stored_name,
            "mime_type": mime_type,
            "kind": kind,
            "size_bytes": size_bytes,
            "extracted_text": extracted_text,
            "created_at": now,
        }

    async def get_attachment(self, attachment_id: str) -> dict[str, Any] | None:
        cursor = await self.conn.execute(
            "SELECT * FROM attachments WHERE id = ?",
            (attachment_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row is not None else None

    async def list_system_prompts(self) -> list[dict[str, Any]]:
        cursor = await self.conn.execute(
            "SELECT id, name, content, created_at FROM system_prompts ORDER BY name ASC"
        )
        return [dict(r) for r in await cursor.fetchall()]

    async def create_system_prompt(self, name: str, content: str) -> dict[str, Any]:
        prompt_id = uuid.uuid4().hex
        now = utcnow_iso()
        await self.conn.execute(
            "INSERT INTO system_prompts (id, name, content, created_at) VALUES (?, ?, ?, ?)",
            (prompt_id, name, content, now),
        )
        await self.conn.commit()
        return {"id": prompt_id, "name": name, "content": content, "created_at": now}

    async def delete_system_prompt(self, prompt_id: str) -> bool:
        cursor = await self.conn.execute("DELETE FROM system_prompts WHERE id = ?", (prompt_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def get_preferences(self, default_model: str) -> dict[str, Any]:
        cursor = await self.conn.execute("SELECT key, value_json FROM preferences")
        rows = await cursor.fetchall()
        prefs: dict[str, Any] = {
            "default_model": default_model,
            "theme": "dark",
            "stream_responses": True,
            "default_parameters": {
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40,
                "num_ctx": 4096,
                "repeat_penalty": 1.1,
            },
        }
        for row in rows:
            prefs[row["key"]] = json.loads(row["value_json"])
        return prefs

    async def update_preferences(self, updates: dict[str, Any], default_model: str) -> dict[str, Any]:
        now = utcnow_iso()
        for key, value in updates.items():
            if value is not None:
                await self.conn.execute(
                    """
                    INSERT INTO preferences (key, value_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
                    """,
                    (key, json.dumps(value), now),
                )
        await self.conn.commit()
        return await self.get_preferences(default_model)

    @staticmethod
    def _row_to_conversation(row: aiosqlite.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "model": row["model"],
            "system_prompt": row["system_prompt"],
            "parameters": json.loads(row["parameters_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
