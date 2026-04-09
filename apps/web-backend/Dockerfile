FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/ apps/
COPY libs/ libs/

RUN find apps -type f ! -name 'pyproject.toml' -delete && \
    find libs -type f ! -name 'pyproject.toml' -delete

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package web-backend

COPY apps/web-backend ./apps/web-backend
COPY libs/ ./libs/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package web-backend

RUN --mount=type=cache,target=/root/.cache/huggingface \
    HF_HOME=/root/.cache/huggingface \
    /app/.venv/bin/python - <<'PY'
from pathlib import Path

from sentence_transformers import SentenceTransformer

target = Path("/opt/models/all-MiniLM-L6-v2")
target.parent.mkdir(parents=True, exist_ok=True)
SentenceTransformer("all-MiniLM-L6-v2").save(str(target))
PY


FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /opt/models /opt/models

ENV PATH="/app/.venv/bin:$PATH" \
    MLCORE_EMBEDDING_MODEL_PATH=/opt/models/all-MiniLM-L6-v2 \
    PORT=8080

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "web_backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
