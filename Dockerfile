# syntax=docker/dockerfile:1

FROM node:24-trixie-slim AS node-runtime

FROM python:3.13-slim AS base

LABEL org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.source="https://github.com/natsteff/forge-gamesheets"

ARG FORGE_GAMESHEETS_VERSION=development
ARG FORGE_GAMESHEETS_REVISION
ARG FORGE_GAMESHEETS_BUILD_DATE

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FORGE_GAMESHEETS_VERSION=${FORGE_GAMESHEETS_VERSION} \
    FORGE_GAMESHEETS_REVISION=${FORGE_GAMESHEETS_REVISION} \
    FORGE_GAMESHEETS_BUILD_DATE=${FORGE_GAMESHEETS_BUILD_DATE}

WORKDIR /app

# Pull current Debian security fixes even when the upstream Python image tag has
# not yet been rebuilt after a base-package advisory. Debian 13 ships an EOL
# Node 20, so use the supported LTS binary from the official Node image instead.
RUN apt-get update \
    && apt-get upgrade --yes \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/LICENSE /usr/local/share/doc/node/LICENSE
COPY scripts/check_node_runtime.mjs /usr/local/lib/forge/check-node-runtime.mjs
RUN node /usr/local/lib/forge/check-node-runtime.mjs

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

CMD ["uvicorn", "app.runtime:app", "--host", "0.0.0.0", "--port", "8000"]

# Local development keeps the established container test commands available.
FROM base AS development
USER root
COPY tests ./tests
COPY docs ./docs
COPY PROJECT_PLAN.md ./
COPY Dockerfile compose.yml .env.example ./
COPY scripts ./scripts
COPY .github/workflows ./.github/workflows
RUN pip install --no-cache-dir ".[dev]"
USER forge-gamesheets

# The default/published image contains neither tests nor development tools.
FROM base AS runtime
USER root
# pip and its bundled libraries are build tools, not runtime dependencies.
RUN python -m pip uninstall --yes pip
USER forge-gamesheets
