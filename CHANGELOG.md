# Changelog

## [0.2.0] - 2026-11-16

### Added
- System prompt preset manager and model deletion controls in the web workspace UI.
- Synchronous chat and invalid-attachment error-path integration tests.
- Comprehensive README with Mermaid architecture diagram, API table, and usage examples.

## [0.1.0] - 2026-11-16

### Added
- FastAPI backend with Ollama REST API integration (`/api/tags`, `/api/chat`, `/api/pull`, `/api/show`, `/api/delete`).
- Server-Sent Events (SSE) streaming chat and SQLite persistence for conversations, messages, system prompts, and preferences.
- Safe file and image upload handling with magic-byte verification, UTF-8 validation, and base64 vision forwarding.
- Responsive web UI and Docker Compose deployment configuration.
