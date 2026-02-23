# AGENTS.md — Coding Agent Guide for ticket-forge

## Project Overview

ticket-forge is a monorepo for an ML-powered ticket assignment system. It ingests GitHub issues, builds engineer skill profiles from resumes and ticket history (using Experience Decay), and trains models to predict ticket resolution time. The stack is Python 3.12, FastAPI, Postgres + pgvector, and Astro (frontend).

## Repository Layout

```
apps/
  training/         # ML training pipeline, ETL (ingest + postload), bias analysis
  web-backend/      # FastAPI REST API (routes → services → models)
  web-frontend/     # Astro frontend
libs/
  ml-core/          # Shared ML utilities: embeddings, keywords, profile updater
  shared/           # Cross-cutting: configuration, logging, caching
scripts/postgres/   # DB init scripts (extensions, schema)
terraform/          # GCP infrastructure
notebooks/          # Jupyter exploration
data/               # DVC-tracked datasets
models/             # DVC-tracked trained model artifacts
```

Workspace packages are managed by **uv** (see `[tool.uv.workspace]` in the root `pyproject.toml`). Internal dependencies (`ml-core`, `shared`) are declared as workspace sources — never install them from PyPI.

## Essential Commands (Justfile)

All commands run from the **repo root** via [just](https://just.systems). The Justfile is the single source of truth for running tasks.

| Command | Purpose |
|---|---|
| `just` | Install all deps (Python, Node, pre-commit, DVC) |
| `just pytest [args]` | Run Python tests (args forwarded to pytest) |
| `just pylint [paths]` | Lint + format + type-check (`ruff check --fix`, `ruff format`, `pyright`) |
| `just pycheck [paths]` | Lint **then** test in one step |
| `just check` | Full repo check (Python + Terraform) |
| `just train [args]` | Run the training pipeline |

### Development lifecycle

1. **Write code** — implement the change.
2. **Comment it** — add Google-style docstrings (`"""Summary.\n\nArgs:\n    ...\n"""`) on all public functions, classes, and modules.
3. **Lint it** — `just pylint <changed paths>`.
4. **Test it** — `just pytest <test files>`.

Always lint before committing. Pre-commit hooks enforce this automatically.

## Coding Standards

### Python style

- **Python ≥ 3.12** — use modern syntax (`X | Y` unions, `list[str]` generics).
- **Formatter / linter**: ruff (line-length 88, indent-width 2, target py312).
- **Type checker**: pyright in standard mode.
- **Docstrings**: Google convention. Every public class, method, and function must have one.
- **Imports**: absolute only — relative imports are banned (`ban-relative-imports = "all"`).
- **Error messages**: use `msg = "..."` then `raise FooError(msg)` — never put string literals directly in `raise` (enforced by ruff `EM`).

### Best practices

- **DRY** — never duplicate logic. If two modules need the same formula, extract it into `libs/ml-core` or `libs/shared`. Example: the Experience Decay formula lives in `ProfileUpdater` and is consumed by both the numpy path (`update_on_ticket_completion`) and the SQL path (`build_profile_update_query`).
- **Use abstractions** — prefer calling library code over re-implementing. Use `get_embedding_service()` and `get_keyword_extractor()` singletons from `ml-core` rather than constructing models directly.
- **Separate concerns in API code** — the web-backend follows a strict layered pattern:
  - `routes/` — FastAPI routers. Thin handlers that parse requests and call services. No business logic.
  - `services/` — Business logic and orchestration. May call `ml-core` or the database.
  - `models/` — Pydantic request/response models and DB data classes. No side effects.
- **ETL pipeline** — `apps/training/training/etl/` separates:
  - `ingest/` — data acquisition (scrapers, CSV conversion, resume extraction, coldstart).
  - `postload/` — post-ingestion processing (ticket replay for profile history).
- **Configuration** — use `shared.configuration.Paths` for all file paths. Use `shared.logging.get_logger(__name__)` for logging. Never hard-code paths or use `print()` for diagnostics.

### Documentation

- Every module (app or lib) has a `README.md` at its root (e.g. `apps/training/README.md`, `libs/ml-core/README.md`). The repo itself has a root `README.md`.
- **No other locations** — do not create README files in sub-directories within a module.
- When you change a module's public API, add a feature, or change its setup, **update that module's `README.md`** to keep it accurate.
- If a change affects cross-cutting concerns (new Justfile commands, schema changes, new libraries, updated best practices), **update `AGENTS.md`** as well.

### Module structure

- All code lives inside a **module**. A module is either an **app** (`apps/<name>/`) or a **lib** (`libs/<name>/`).
- Python modules contain a `pyproject.toml` and a package directory matching the module name (e.g. `apps/training/training/`).
- TypeScript modules contain a `package.json`. TypeScript is **only** used for the frontend (`apps/web-frontend`).
- Never place standalone scripts or business logic outside of a module. Utility scripts belong in the relevant app or lib.

### Workspace conventions (uv + npm)

- **uv workspaces** — the root `pyproject.toml` declares all Python members under `[tool.uv.workspace]`. When adding a new Python module, register it there.
- Internal Python dependencies (`ml-core`, `shared`) are declared as **workspace sources** in each consumer's `pyproject.toml` under `[tool.uv.sources]` — e.g. `ml-core = { workspace = true }`. Never publish or install them from PyPI.
- **npm workspaces** — the root `package.json` declares frontend packages. Node dependencies are managed at the root; do not run `npm install` inside individual packages.
- After changing any `pyproject.toml` or `package.json`, run `just` from the repo root to sync.

### Testing

- Tests live in `tests/` directories adjacent to their source package.
- **Prefer meaningful end-to-end style tests over chasing coverage numbers.** A test should verify a real user-facing behaviour or integration path, not just exercise a line of code. If a test doesn't fail when the feature is broken, delete it.
- Mock external dependencies (DB, embedding models) — never require a running database for unit tests.
- Use `pytest` fixtures and `unittest.mock.patch` / `MagicMock` for isolation.
- Test file naming: `test_<module>.py`.

## Database (Postgres + pgvector)

Started via `docker compose up -d`. Connection from the host: `postgresql://ticketforge:root@localhost:5433/ticketforge`.

### Schema (scripts/postgres/init/)

Extensions: `vector` (pgvector), `pg_trgm`.

**Three core tables:**

| Table | Key columns | Notes |
|---|---|---|
| `users` | `member_id` (BIGINT PK), `github_username` (UNIQUE), `profile_vector` (vector(384)), `resume_base_vector` (vector(384) nullable), `skill_keywords` (tsvector), `tickets_closed_count` | `resume_base_vector IS NULL` → stub profile (no resume yet). `profile_vector` evolves via Experience Decay. |
| `tickets` | `ticket_id` (TEXT PK), `title`, `description`, `ticket_vector` (vector(384)), `labels` (JSONB), `status` (enum: open/in-progress/closed) | Vectors indexed with IVFFlat for cosine similarity. |
| `assignments` | `assignment_id` (UUID PK), `ticket_id` → tickets, `engineer_id` → users | UNIQUE(ticket_id, engineer_id). |

All vectors are 384-dimensional (from `all-MiniLM-L6-v2`). Hybrid search is supported via both vector cosine similarity and GIN-indexed tsvector/full-text search.

### Experience Decay formula

When an engineer completes a ticket:

```
profile_vector ← α · profile_vector + (1 − α) · ticket_vector
```

Default α = 0.95 (95% memory, 5% new signal). This is implemented in `ml_core.profiles.updater.ProfileUpdater` — both as a numpy operation and as a parameterised SQL query. Always use `ProfileUpdater` rather than reimplementing the formula.

## Key Libraries (internal)

### ml-core (`libs/ml-core/ml_core/`)

- `embeddings.get_embedding_service()` — singleton `SentenceTransformer` wrapper. Returns 384-dim numpy arrays.
- `keywords.get_keyword_extractor()` — regex + dictionary-based skill extraction from text.
- `profiles.ProfileUpdater` — Experience Decay for engineer profiles (numpy + SQL).
- `profiles.EngineerProfile` — dataclass with `to_dict()` / `from_dict()` serialization.

### shared (`libs/shared/shared/`)

- `configuration.Paths` — `repo_root`, `data_root`, `models_root`.
- `logging.get_logger(name)` — pre-configured logger with consistent format.
