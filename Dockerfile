FROM node:22-bookworm-slim AS javascript

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

COPY --from=javascript /usr/local/bin/node /usr/local/bin/node

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git libopus0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN mkdir -p cache normalized storage

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

CMD ["python", "app.py"]