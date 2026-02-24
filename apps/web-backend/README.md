# Web Backend

FastAPI web service for serving ML model predictions and handling business logic.

## Overview

RESTful API backend that:
- Serves predictions from trained ML models
- Handles ticket assignment recommendations
- Provides health checks and status endpoints

## Quick Start

### Run Development Server

```bash
# From repo root
cd apps/web-backend
uv run uvicorn web_backend.main:app --reload
```

Server will be available at `http://localhost:8000`

### API Documentation

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Structure

```
web_backend/
├── routes/            # FastAPI routers (thin handlers)
├── services/          # Business logic and orchestration
├── models/            # Pydantic request/response models
└── main.py            # FastAPI application entry point
```

**Architecture:** Strict separation of concerns following a layered pattern:
- **Routes** — Parse requests, call services, return responses. No business logic.
- **Services** — Orchestrate operations, call `ml-core` utilities, interact with database.
- **Models** — Pydantic schemas for validation. No side effects.

## Dependencies

- **FastAPI** - Modern web framework
- **Pydantic** - Data validation
- **ml-core** - ML utilities and models

See `pyproject.toml` for exact versions.

## Testing

```bash
just pytest apps/web-backend/tests/
```
