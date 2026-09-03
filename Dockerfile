# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base

ARG FORGE_GAMESHEETS_VERSION=development
ARG FORGE_GAMESHEETS_REVISION
ARG FORGE_GAMESHEETS_BUILD_DATE

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FORGE_GAMESHEETS_VERSION=${FORGE_GAMESHEETS_VERSION} \
    FORGE_GAMESHEETS_REVISION=${FORGE_GAMESHEETS_REVISION} \
    FORGE_GAMESHEETS_BUILD_DATE=${FORGE_GAMESHEETS_BUILD_DATE}

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --no-cache-dir .

# Stable IDs make permissions for bind-mounted application data predictable.
RUN addgroup --system --gid 10001 forge-gamesheets \
    && adduser --system --uid 10001 --ingroup forge-gamesheets forge-gamesheets \
    && mkdir -p /library /data \
    && chown -R forge-gamesheets:forge-gamesheets /app /data

USER forge-gamesheets

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Local development keeps the established container test commands available.
FROM base AS development
USER root
COPY tests ./tests
COPY Dockerfile compose.yml .env.example ./
COPY scripts ./scripts
COPY .github/workflows ./.github/workflows
RUN pip install --no-cache-dir ".[dev]"
USER forge-gamesheets

# The default/published image contains neither tests nor development tools.
FROM base AS runtime
