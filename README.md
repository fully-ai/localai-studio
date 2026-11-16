# LocalAI Studio

Self-hosted web workspace and REST/SSE gateway for managing and interacting with local [Ollama](https://ollama.com/) language and vision models.

## Purpose

Running local LLMs through CLI tools alone makes multi-turn conversation management, parameter tuning, system prompt reuse, and file/image attachments cumbersome. LocalAI Studio provides a lightweight, self-hosted web interface and structured API backed by SQLite so all conversations, prompts, and attachments remain on your machine.

## Features

- **Ollama Model Management**: List installed models, inspect model details, pull new models, and remove unused models via `/api/models`.
- **Streaming & Non-Streaming Chat**: Real-time token streaming over Server-Sent Events (SSE) alongside synchronous JSON responses.
- **Persistent Conversations**: Create, rename, update model/parameters, and delete conversations stored in SQLite (WAL mode).
- **File & Vision Attachments**: Upload UTF-8 text/code files (`.txt`, `.md`, `.py`, `.json`, `.yaml`, etc.) and images (`.png`, `.jpg`, `.webp`, `.gif`) with magic-byte verification, size limits, and UUID-based storage to prevent path traversal.
- **System Prompts & Preferences**: Save reusable system prompts and persist UI theme/model defaults.
- **Docker Support**: Ready-to-run `Dockerfile` and `compose.yaml` pairing LocalAI Studio with an Ollama container.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, Uvicorn, HTTPX, aiosqlite, Pydantic v2
- **Frontend**: Vanilla HTML/CSS/JS (dark & light themes, zero build step)
- **Storage**: SQLite + local filesystem attachment store

## System Requirements

- Python 3.11+
- Running Ollama instance (local or via Docker)

## Installation

```bash
git clone https://github.com/fully-ai/localai-studio.git
cd localai-studio
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

| Variable | Default | Description |
| --- | --- | --- |
| `LOCALAI_HOST` | `127.0.0.1` | Bind address |
| `LOCALAI_PORT` | `8080` | HTTP listen port |
| `LOCALAI_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API base URL |
| `LOCALAI_DATA_DIR` | `./data` | SQLite database and upload directory |
| `LOCALAI_MAX_UPLOAD_BYTES` | `10485760` | Max attachment size in bytes (10 MiB) |
| `LOCALAI_DEFAULT_MODEL` | `llama3.2` | Default model identifier |

## Running

```bash
localai-studio
```

Open `http://127.0.0.1:8080` in your browser.

## API Overview

- `GET /api/health` — Application & Ollama connectivity status
- `GET /api/models`, `POST /api/models/pull`, `GET /api/models/{name}`, `DELETE /api/models/{name}`
- `GET /api/conversations`, `POST /api/conversations`, `GET /api/conversations/{id}`, `PATCH /api/conversations/{id}`, `DELETE /api/conversations/{id}`
- `POST /api/conversations/{id}/messages` — Send user prompt (SSE stream when `stream: true`)
- `POST /api/files` — Upload validated text or image attachment
- `GET /api/prompts`, `POST /api/prompts`, `DELETE /api/prompts/{id}`
- `GET /api/preferences`, `PATCH /api/preferences`

## Architecture

```
Browser UI (/static) <──HTTP/SSE──> FastAPI (app.py)
                                       ├── SQLite (db.py)
                                       ├── Upload Store (files.py)
                                       └── OllamaClient (ollama_client.py) ──> Ollama API
```

## Testing

```bash
ruff check src tests
mypy src
pytest -v
```

## Docker Deployment

```bash
docker compose up -d --build
```

## Security Notes

- Binds to `127.0.0.1` by default; place behind an authenticated reverse proxy before exposing on untrusted networks.
- Uploaded files are validated by extension, size, and magic bytes / UTF-8 decoding, and stored under generated UUID filenames.

## Known Limitations

- Single-user local workspace without built-in multi-tenant authentication.
- PDF text extraction is not included; plain text, code, and images are supported.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
