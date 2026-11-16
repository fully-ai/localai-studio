# Architecture — LocalAI Studio

## Components

- `src/localai_studio/app.py`: FastAPI application factory exposing REST and SSE endpoints, CORS middleware, and static UI serving.
- `src/localai_studio/ollama_client.py`: Async `httpx` client communicating with Ollama (`/api/version`, `/api/tags`, `/api/pull`, `/api/show`, `/api/delete`, `/api/chat`).
- `src/localai_studio/db.py`: SQLite (WAL mode) persistence for `conversations`, `messages`, `attachments`, `system_prompts`, and `preferences`.
- `src/localai_studio/files.py`: Attachment validator performing filename sanitization, size checks, image magic-byte verification, UTF-8 decoding, and UUID storage naming.
- `src/localai_studio/static/`: Browser workspace supporting conversation management, parameter tuning, attachments, and SSE token rendering.

## Data Flow

1. Client sends a chat message via `POST /api/conversations/{id}/messages`.
2. Backend persists the user message in SQLite, resolves attached text snippets or base64-encoded images, and forwards conversation history to Ollama `/api/chat`.
3. Streaming chunks from Ollama NDJSON are converted into SSE `delta` events and persisted as the assistant message upon completion.
