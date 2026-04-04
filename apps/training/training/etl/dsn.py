"""Utilities for Postgres DSN resolution in ETL tasks.

These helpers normalize SQLAlchemy-style Postgres URLs into libpq-compatible
URLs for direct psycopg2 usage.
"""

from __future__ import annotations

import os


def normalize_psycopg2_dsn(dsn: str) -> str:
  """Normalize a Postgres DSN for psycopg2/libpq consumers.

  Args:
      dsn: Input DSN string.

  Returns:
      DSN compatible with psycopg2/libpq.
  """
  if dsn.startswith("postgresql+") and "://" in dsn:
    _, remainder = dsn.split("://", maxsplit=1)
    return f"postgresql://{remainder}"

  return dsn


def resolve_postgres_dsn(
  dsn: str | None = None,
  env_var: str = "DATABASE_URL",
) -> str:
  """Resolve and normalize a Postgres DSN.

  Args:
      dsn: Explicit DSN override.
      env_var: Environment variable to read when dsn is not provided.

  Returns:
      Normalized psycopg2-compatible DSN.

  Raises:
      RuntimeError: If no DSN is available.
  """
  resolved = dsn or os.environ.get(env_var)
  if not resolved:
    msg = f"No Postgres DSN provided. Pass `dsn` or set {env_var}."
    raise RuntimeError(msg)

  return normalize_psycopg2_dsn(resolved)
