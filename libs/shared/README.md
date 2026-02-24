# Shared

Common utilities and helpers shared across the monorepo.

## Overview

Utilities library providing:
- Configuration management (paths, settings, environment variables)
- Caching decorators (filesystem and JSON)
- Logging utilities with consistent format
- Global constants and helpers

## Structure

```
shared/
├── cache.py              # Caching decorators (@cache_json, @cache_fs)
├── configuration.py      # Paths class, getenv/getenv_or helpers
└── logging.py            # get_logger() with standardized format
```

**Usage:** All modules should use `shared.configuration.Paths` for file paths, `shared.logging.get_logger(__name__)` for logging, and `shared.configuration.getenv/getenv_or` for environment variables. Never hard-code paths or use bare `os.getenv()`.
