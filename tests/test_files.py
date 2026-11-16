"""Unit tests for file upload validation and safe storage."""

from pathlib import Path

import pytest

from localai_studio.files import FileValidationError, load_image_base64, sanitize_filename, store_upload

VALID_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"


def test_sanitize_filename_strips_traversal() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("my report (final).txt") == "my_report_final_.txt"


def test_store_valid_text_and_image(tmp_path: Path) -> None:
    txt = store_upload(tmp_path, "notes.md", b"# Hello\nWorld", max_bytes=1024)
    assert txt.kind == "text"
    assert "Hello" in txt.extracted_text
    assert (tmp_path / txt.stored_name).is_file()

    img = store_upload(tmp_path, "pixel.png", VALID_PNG, max_bytes=1024)
    assert img.kind == "image"
    assert img.mime_type == "image/png"
    b64 = load_image_base64(tmp_path, img.stored_name)
    assert len(b64) > 0


def test_rejects_spoofed_image_and_binary_text(tmp_path: Path) -> None:
    with pytest.raises(FileValidationError, match="does not match image"):
        store_upload(tmp_path, "fake.png", b"not a png", max_bytes=1024)

    with pytest.raises(FileValidationError, match="NUL"):
        store_upload(tmp_path, "bad.txt", b"hello\x00world", max_bytes=1024)

    with pytest.raises(FileValidationError, match="Unsupported"):
        store_upload(tmp_path, "payload.exe", b"MZ", max_bytes=1024)

    with pytest.raises(FileValidationError, match="exceeds maximum"):
        store_upload(tmp_path, "big.txt", b"a" * 2048, max_bytes=1024)
