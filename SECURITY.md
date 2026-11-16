# Security Policy

## Reporting a Vulnerability

Please report security issues privately by opening a GitHub Security Advisory on this repository. Include steps to reproduce, affected versions, and potential impact.

## Security Design Notes

- File uploads are restricted by extension, size limit, and magic-byte/UTF-8 validation.
- Stored filenames use generated UUIDs to prevent path traversal.
- Bind `LOCALAI_HOST` to `127.0.0.1` unless placing the service behind an authenticated reverse proxy.
