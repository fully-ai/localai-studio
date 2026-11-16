FROM python:3.12-slim

WORKDIR /app

RUN useradd --create-home --shell /bin/bash appuser

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

USER appuser

ENV LOCALAI_HOST=0.0.0.0 \
    LOCALAI_PORT=8080 \
    LOCALAI_DATA_DIR=/data

VOLUME ["/data"]
EXPOSE 8080

CMD ["localai-studio"]
