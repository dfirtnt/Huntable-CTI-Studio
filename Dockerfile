# syntax=docker/dockerfile:1
#
# Role-specific runtime targets. `development-runtime` remains the temporary
# compatibility target for services not yet migrated to a narrower role.

FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1

WORKDIR /app

# Build-only packages stay in this stage; no runtime target inherits them.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

# Keep this narrow layer before application source. sigma_atom_similarity is a
# workspace package and must be present for each role's locked resolution.
COPY pyproject.toml uv.lock ./
COPY sigma_atom_similarity/ ./sigma_atom_similarity/


FROM builder AS builder-web
RUN UV_PROJECT_ENVIRONMENT=/opt/venvs/web uv sync --frozen --no-default-groups


FROM builder AS builder-ingest
RUN UV_PROJECT_ENVIRONMENT=/opt/venvs/ingest uv sync --frozen --no-default-groups --group ingest --group semantic


FROM builder AS builder-workflow
RUN UV_PROJECT_ENVIRONMENT=/opt/venvs/workflow uv sync --frozen --no-default-groups --group workflow


FROM builder AS builder-semantic
RUN UV_PROJECT_ENVIRONMENT=/opt/venvs/semantic uv sync --frozen --no-default-groups --group semantic --group mcp


FROM builder AS builder-development
RUN UV_PROJECT_ENVIRONMENT=/opt/venvs/development uv sync --frozen --no-default-groups --group ingest --group semantic --group workflow --group mcp --group docs


FROM python:3.11-slim AS runtime-os

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH=/app/.venv/bin:$PATH \
    TZ=America/New_York

WORKDIR /app

# Shared runtime libraries only. Role-specific stages install their own extras.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libgomp1 \
        libpq5 \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash cti_user \
    && mkdir -p /app/data /app/logs


FROM runtime-os AS runtime-app

# Copy ownership at layer creation; never recursively chown the application
# tree in a later layer.
COPY --from=builder-web --chown=cti_user:cti_user /opt/venvs/web /app/.venv
COPY --chown=cti_user:cti_user . .

USER cti_user


FROM runtime-os AS web-runtime

# The web service still invokes Docker-backed backup and management operations.
# Keep only this capability until the Docker-socket remediation target replaces
# it with a narrowly scoped mechanism. Browser layers remain excluded; Codex
# remains because web routes probe its subscription/provider capability, and
# Tesseract remains because the web health surface probes its live availability.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gnupg \
        lsb-release \
        nodejs \
        npm \
        tesseract-ocr \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/* \
    && usermod -aG root cti_user

ARG CODEX_VERSION=0.147.0
RUN npm install --global @openai/codex@${CODEX_VERSION} \
    && npm cache clean --force

COPY --from=builder-web --chown=cti_user:cti_user /opt/venvs/web /app/.venv
COPY --chown=cti_user:cti_user . .

USER cti_user

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "src.web.modern_main:app", "--host", "0.0.0.0", "--port", "8001"]


FROM runtime-app AS scheduler-runtime

CMD ["celery", "-A", "src.worker.celery_app", "beat", "--loglevel=info"]


# Source-collection worker. Retains Playwright/Chromium and Tesseract for
# scraping and OCR, plus the local Torch + sentence-transformers stack used by
# extraction paths. Excludes Codex and Docker
# CLI/socket access -- it has no Codex or host-docker execution paths.
FROM runtime-os AS ingest-worker-runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        libglib2.0-0 \
        libnspr4 \
        libnss3 \
        libdbus-1-3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libxcb1 \
        libxkbcommon0 \
        libatspi2.0-0 \
        libx11-6 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libcairo2 \
        libpango-1.0-0 \
        libasound2 \
        libxcursor1 \
        libgtk-3-0 \
        libgdk-pixbuf-2.0-0 \
        libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder-ingest --chown=cti_user:cti_user /opt/venvs/ingest /app/.venv

# Run the Playwright-maintained dependency check with the ingest environment
# present. Do not mask failure: the explicit package list above can drift.
RUN python -m playwright install-deps chromium

COPY --chown=cti_user:cti_user . .

USER cti_user

RUN python -m playwright install chromium


# Workflow worker. Retains LangGraph and the pinned Codex
# app-server binary for the optional Codex workflow provider, including the
# existing Codex auth-volume compatibility. Excludes Playwright/Chromium,
# Tesseract/OCR, Docker CLI, and Docker socket-group access -- the workflow
# worker has no browser, OCR, or host-docker execution paths.
FROM runtime-os AS workflow-worker-runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gnupg \
        lsb-release \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

ARG CODEX_VERSION=0.147.0
RUN npm install --global @openai/codex@${CODEX_VERSION} \
    && npm cache clean --force

COPY --from=builder-workflow --chown=cti_user:cti_user /opt/venvs/workflow /app/.venv
COPY --chown=cti_user:cti_user . .

USER cti_user


# CLI / MCP semantic-search target. Retains Torch + sentence-transformers so
# local embeddings work with LM Studio unavailable. Browser,
# OCR, Codex, and Docker CLI are excluded. Note: the optional `cli backup`
# system-backup subcommand shells out to `docker exec`; because this target has
# no Docker CLI and the `cli` Compose service does not mount the Docker socket,
# that subcommand is not functional inside the container. Backups run through
# the web service (which retains the socket) or host scripts instead. Python
# import/entrypoint compatibility for `cli` and `mcp_http` is otherwise intact.
FROM runtime-os AS semantic-tools-runtime

COPY --from=builder-semantic --chown=cti_user:cti_user /opt/venvs/semantic /app/.venv
COPY --chown=cti_user:cti_user . .

USER cti_user


# Compatibility target for services that still require the monolithic runtime.
# Subsequent role-target tasks will replace this with ingest, workflow, and
# semantic-tools targets and move each Compose service off this stage.
FROM runtime-os AS development-runtime

COPY --from=builder-development --chown=cti_user:cti_user /opt/venvs/development /app/.venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gnupg \
        lsb-release \
        nodejs \
        npm \
        postgresql-client \
        tesseract-ocr \
        tesseract-ocr-eng \
        libglib2.0-0 \
        libnspr4 \
        libnss3 \
        libdbus-1-3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libxcb1 \
        libxkbcommon0 \
        libatspi2.0-0 \
        libx11-6 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libcairo2 \
        libpango-1.0-0 \
        libasound2 \
        libxcursor1 \
        libgtk-3-0 \
        libgdk-pixbuf-2.0-0 \
        libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Docker access remains only in the compatibility target until the dedicated
# Docker-socket remediation task supplies a narrower replacement.
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

ARG CODEX_VERSION=0.147.0
RUN npm install --global @openai/codex@${CODEX_VERSION} \
    && npm cache clean --force \
    && python -m playwright install-deps chromium

COPY --chown=cti_user:cti_user . .

# Docker Desktop exposes the mounted socket as root:root. This temporary
# compatibility target preserves the existing behavior until that mount is
# removed from the web service.
RUN usermod -aG root cti_user

USER cti_user
RUN python -m playwright install chromium

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "src.web.modern_main:app", "--host", "0.0.0.0", "--port", "8001"]
