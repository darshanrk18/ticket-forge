# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

# Define which app we are building (defaults to training)
ARG APP_NAME=training

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

WORKDIR /app

# 1. Copy Workspace Metadata
COPY pyproject.toml uv.lock ./
COPY apps/ apps/
COPY libs/ libs/

# Remove source code but keep pyproject.toml files to cache dependency install
RUN find apps -type f ! -name 'pyproject.toml' -delete && \
    find libs -type f ! -name 'pyproject.toml' -delete

# 2. Install dependencies (Third-party only)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package ${APP_NAME}

# 3. Copy actual source code back in
COPY apps/${APP_NAME} ./apps/${APP_NAME}
COPY libs/ ./libs/

# 4. Install workspace packages as REAL packages (not editable)
#    --no-editable ensures they are copied into site-packages
#    so they survive the multi-stage copy without broken path references
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package ${APP_NAME}


# --- Stage 2: Runtime ---
FROM python:3.12-slim AS runtime

ARG APP_NAME=training
ENV APP_NAME=${APP_NAME}

# Install tesseract-ocr and language data
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        tesseract-ocr \
        tesseract-ocr-eng \
        libleptonica-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy ONLY the venv — no need for source dirs since packages are non-editable
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["python"]
