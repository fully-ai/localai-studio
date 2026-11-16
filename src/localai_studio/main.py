"""CLI entrypoint for running LocalAI Studio."""

from __future__ import annotations

import logging

import uvicorn

from localai_studio.app import create_app
from localai_studio.config import Settings


def cli() -> None:
    settings = Settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    cli()
