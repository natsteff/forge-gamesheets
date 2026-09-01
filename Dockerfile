# syntax=docker/dockerfile:1

FROM python:3.13-slim

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
COPY tests ./tests

RUN pip install --no-cache-dir ".[dev]"

# Stable IDs make permissions for bind-mounted application data predictable.
RUN addgroup --system --gid 10001 forge-gamesheets \
    && adduser --system --uid 10001 --ingroup forge-gamesheets forge-gamesheets \
    && mkdir -p /library /data \
    && chown -R forge-gamesheets:forge-gamesheets /app /data

USER forge-gamesheets

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
