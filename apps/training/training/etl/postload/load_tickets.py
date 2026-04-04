"""Run scrape -> transform -> Postgres load for GitHub tickets."""

import argparse
import asyncio
import math
from typing import Iterable

import psycopg2
from psycopg2.extras import Json
from training.etl.dsn import resolve_postgres_dsn
from training.etl.ingest.scrape_github_issues_improved import scrape_all_issues
from training.etl.transform.run_transform import transform_records

EMBEDDING_DIM = 384


def _vector_to_pg(value: object) -> str:
  """Convert an embedding to pgvector text format `[x,y,...]`."""
  if value is None:
    msg = "embedding is missing"
    raise ValueError(msg)

  tolist_fn = getattr(value, "tolist", None)
  if callable(tolist_fn):
    value = tolist_fn()

  if not isinstance(value, list):
    msg = f"embedding must be a list, got: {type(value).__name__}"
    raise TypeError(msg)

  if len(value) != EMBEDDING_DIM:
    msg = f"embedding must have {EMBEDDING_DIM} values, got {len(value)}"
    raise ValueError(msg)

  return "[" + ",".join(map(str, value)) + "]"


def _labels_to_json(value: object) -> list[str]:
  """Normalize labels into a JSONB-friendly list of strings."""
  if value is None:
    return []

  if isinstance(value, list):
    return [str(v).strip() for v in value if str(v).strip()]

  if isinstance(value, str):
    if not value.strip():
      return []
    return [part.strip() for part in value.split(",") if part.strip()]

  return [str(value)]


def _map_status(issue_type: object, state: object) -> str:
  """Map source issue state to ticket_status enum."""
  issue_type_s = str(issue_type or "").strip().lower()
  state_s = str(state or "").strip().lower()

  if issue_type_s == "closed" or state_s == "closed":
    return "closed"
  if issue_type_s == "open_assigned":
    return "in-progress"
  return "open"


def _optional_timestamptz(value: object) -> str | None:
  """Return a safe timestamp string or None for invalid/empty values."""
  if value is None:
    return None

  if isinstance(value, float) and not math.isfinite(value):
    return None

  text = str(value).strip()
  if not text:
    return None

  if text.lower() in {"nan", "nat", "none", "null"}:
    return None

  return text


def upsert_tickets(
  tickets: Iterable[dict],
  dsn: str | None = None,
) -> int:
  """Upsert transformed tickets into the `tickets` table."""
  resolved_dsn = resolve_postgres_dsn(dsn)

  sql = """
  INSERT INTO tickets (
    ticket_id,
    title,
    description,
    ticket_vector,
    labels,
    status,
    resolution_time_actual,
    created_at,
    updated_at
  )
  VALUES (
    %s,
    %s,
    %s,
    %s::vector,
    %s::jsonb,
    %s::ticket_status,
    CASE WHEN %s IS NULL THEN NULL ELSE (%s * interval '1 hour') END,
    COALESCE(%s::timestamptz, now()),
    now()
  )
  ON CONFLICT (ticket_id)
  DO UPDATE SET
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    ticket_vector = EXCLUDED.ticket_vector,
    labels = EXCLUDED.labels,
    status = EXCLUDED.status,
    resolution_time_actual = EXCLUDED.resolution_time_actual,
    created_at = EXCLUDED.created_at,
    updated_at = now()
  """

  processed = 0
  conn = psycopg2.connect(resolved_dsn)

  try:
    with conn, conn.cursor() as cur:
      for ticket in tickets:
        ticket_id = str(ticket.get("id", "")).strip()
        if not ticket_id:
          continue

        title = str(ticket.get("title") or "")
        description = str(ticket.get("normalized_text") or ticket.get("body") or "")
        vector_text = _vector_to_pg(ticket.get("embedding"))
        labels_json = Json(_labels_to_json(ticket.get("labels")))
        status = _map_status(ticket.get("issue_type"), ticket.get("state"))

        hours = ticket.get("completion_hours_business")
        if hours is not None:
          try:
            hours = float(hours)
            if (not math.isfinite(hours)) or hours < 0 or hours > 1000000:
              hours = None
          except (TypeError, ValueError):
            hours = None

        created_at = _optional_timestamptz(ticket.get("created_at"))

        cur.execute(
          sql,
          (
            ticket_id,
            title,
            description,
            vector_text,
            labels_json,
            status,
            hours,
            hours,
            created_at,
          ),
        )
        processed += 1
  except Exception:
    conn.rollback()
    raise
  finally:
    conn.close()

  return processed


def upsert_assignments(
  tickets: Iterable[dict],
  dsn: str | None = None,
) -> tuple[int, int]:
  """Upsert assignments for rows with assignees that exist in `users`."""
  resolved_dsn = resolve_postgres_dsn(dsn)

  sql = """
  INSERT INTO assignments (ticket_id, engineer_id, assigned_at)
  SELECT
    %s,
    u.member_id,
    COALESCE(%s::timestamptz, now())
  FROM users u
  WHERE u.github_username = %s
  ON CONFLICT (ticket_id, engineer_id)
  DO UPDATE SET
    assigned_at = EXCLUDED.assigned_at
  """

  upserted = 0
  missing_user = 0
  conn = psycopg2.connect(resolved_dsn)

  try:
    with conn, conn.cursor() as cur:
      for ticket in tickets:
        ticket_id = str(ticket.get("id", "")).strip()
        assignee = str(ticket.get("assignee") or "").strip()

        if not ticket_id or not assignee:
          continue

        assigned_at = _optional_timestamptz(ticket.get("assigned_at"))
        if assigned_at is None:
          assigned_at = _optional_timestamptz(ticket.get("created_at"))

        cur.execute(sql, (ticket_id, assigned_at, assignee))

        if cur.rowcount == 0:
          missing_user += 1
        else:
          upserted += cur.rowcount
  except Exception:
    conn.rollback()
    raise
  finally:
    conn.close()

  return upserted, missing_user


async def run_pipeline(
  dsn: str | None = None,
  limit_per_state: int | None = None,
) -> int:
  """Execute scrape -> transform -> upsert pipeline end-to-end."""
  print("Step 1/4: Scraping GitHub issues...")
  raw_records = await scrape_all_issues(limit_per_state=limit_per_state)
  print(f"Scraped {len(raw_records)} records")

  print("Step 2/4: Transforming records...")
  transformed = transform_records(raw_records)
  print(f"Transformed {len(transformed)} records")

  print("Step 3/4: Upserting tickets...")
  loaded_tickets = upsert_tickets(transformed, dsn=dsn)
  print(f"Upserted {loaded_tickets} ticket(s) into Postgres")

  print("Step 4/4: Upserting assignments...")
  assigned_count, missing_user_count = upsert_assignments(transformed, dsn=dsn)
  print(f"Upserted {assigned_count} assignment row(s)")
  if missing_user_count:
    print(f"Skipped {missing_user_count} assignment(s): assignee not found in users")

  return loaded_tickets


def main() -> None:
  """CLI runner for end-to-end ticket pipeline."""
  parser = argparse.ArgumentParser(
    description="Run GraphQL scrape, transform, and Postgres load"
  )
  parser.add_argument(
    "--dsn",
    default=None,
    help="Postgres DSN (defaults to DATABASE_URL env var)",
  )
  parser.add_argument(
    "--limit-per-state",
    type=int,
    default=None,
    help="Optional cap per repo/state for quick testing",
  )
  args = parser.parse_args()

  asyncio.run(run_pipeline(dsn=args.dsn, limit_per_state=args.limit_per_state))


if __name__ == "__main__":
  main()
