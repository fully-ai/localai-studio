"""Safe file validation, storage, and content extraction for chat attachments."""

from __future__ import annotations

import base64
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTENSIONS: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

TEXT_EXTENSIONS: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".csv": "text/csv",
    ".py": "text/x-python",
    ".js": "text/javascript",
    ".ts": "text/typescript",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".toml": "text/toml",
    ".log": "text/plain",
}

_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


class FileValidationError(ValueError):
    """Raised when an uploaded file fails security or format validation."""


@dataclass(slots=True)
class StoredAttachment:
    attachment_id: str
    filename: str
    stored_name: str
    mime_type: str
    kind: str
    size_bytes: int
    extracted_text: str


def sanitize_filename(raw_name: str) -> str:
    """Strip directory components and unsafe characters from a filename."""
    base = Path(raw_name).name
    cleaned = _SAFE_FILENAME_RE.sub("_", base).strip("._")
    return cleaned[:120] or "upload"


def _verify_image_magic(ext: str, content: bytes) -> bool:
    if ext == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if ext == ".gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if ext == ".webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


def store_upload(
    upload_dir: Path,
    raw_filename: str,
    content: bytes,
    max_bytes: int,
) -> StoredAttachment:
    """Validate and safely store an uploaded image or text file."""
    if not content:
        raise FileValidationError("Uploaded file is empty.")
    if len(content) > max_bytes:
        raise FileValidationError(f"File exceeds maximum allowed size of {max_bytes} bytes.")

    safe_name = sanitize_filename(raw_filename)
    ext = Path(safe_name).suffix.lower()

    if ext in IMAGE_EXTENSIONS:
        if not _verify_image_magic(ext, content):
            raise FileValidationError(f"File content does not match image extension '{ext}'.")
        kind = "image"
        mime_type = IMAGE_EXTENSIONS[ext]
        extracted_text = ""
    elif ext in TEXT_EXTENSIONS:
        if b"\x00" in content[:4096]:
            raise FileValidationError("Binary NUL bytes detected in text file.")
        try:
            extracted_text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FileValidationError("Text file must be valid UTF-8.") from exc
        kind = "text"
        mime_type = TEXT_EXTENSIONS[ext]
    else:
        raise FileValidationError(f"Unsupported file extension '{ext or '(none)'}'.")

    attachment_id = uuid.uuid4().hex
    stored_name = f"{attachment_id}{ext}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = (upload_dir / stored_name).resolve()
    if target.parent != upload_dir.resolve():
        raise FileValidationError("Invalid upload path.")
    target.write_bytes(content)

    return StoredAttachment(
        attachment_id=attachment_id,
        filename=safe_name,
        stored_name=stored_name,
        mime_type=mime_type,
        kind=kind,
        size_bytes=len(content),
        extracted_text=extracted_text[:50_000],
    )


def load_image_base64(upload_dir: Path, stored_name: str) -> str:
    """Safely read an image attachment from upload_dir and return base64 string."""
    safe_stored = Path(stored_name).name
    target = (upload_dir / safe_stored).resolve()
    if target.parent != upload_dir.resolve() or not target.is_file():
        raise FileNotFoundError(f"Attachment file not found: {safe_stored}")
    return base64.b64encode(target.read_bytes()).decode("ascii")
