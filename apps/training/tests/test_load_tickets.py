"""Unit tests for ticket post-load pipeline."""

from __future__ import annotations

import asyncio
from types import TracebackType
from unittest.mock import patch

from training.etl.postload import load_tickets


class _DummyCursor:
  """Minimal cursor stub for psycopg2 unit tests."""

  def __init__(self, rowcounts: list[int] | None = None) -> None:
    self.executions: list[tuple[str, tuple[object, ...]]] = []
    self._rowcounts = rowcounts or []
    self._idx = 0
    self.rowcount = 1

  def __enter__(self) -> "_DummyCursor":
    """Support context manager usage."""
    return self

  def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb: TracebackType | None,
  ) -> bool:
    """Return False so exceptions are not swallowed."""
    return False

  def execute(self, sql: str, params: tuple[object, ...]) -> None:
    """Record SQL execution and provide configured rowcount."""
    self.executions.append((sql, params))
    if self._idx < len(self._rowcounts):
      self.rowcount = self._rowcounts[self._idx]
      self._idx += 1


class _DummyConn:
  """Minimal connection stub for psycopg2 unit tests."""

  def __init__(self, cursor: _DummyCursor) -> None:
    self._cursor = cursor
    self.closed = False
    self.rolled_back = False

  def __enter__(self) -> "_DummyConn":
    """Support context manager usage."""
    return self

  def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb: TracebackType | None,
  ) -> bool:
    """Return False so exceptions are not swallowed."""
    return False

  def cursor(self) -> _DummyCursor:
    """Return the stub cursor."""
    return self._cursor

  def rollback(self) -> None:
    """Track rollback calls."""
    self.rolled_back = True

  def close(self) -> None:
    """Track connection closure."""
    self.closed = True


class TestHelpers:
  """Helper function behavior tests."""

  def test_optional_timestamptz_filters_invalid_values(self) -> None:
    """Invalid values map to None and valid timestamps pass through."""
    expected = "2026-01-01T00:00:00Z"

    assert load_tickets._optional_timestamptz(None) is None
    assert load_tickets._optional_timestamptz(float("nan")) is None
    assert load_tickets._optional_timestamptz("NaT") is None
    assert load_tickets._optional_timestamptz(" ") is None
    assert load_tickets._optional_timestamptz(expected) == expected

  def test_map_status(self) -> None:
    """Issue type/state values map to DB ticket_status values."""
    assert load_tickets._map_status("closed", "open") == "closed"
    assert load_tickets._map_status("open_assigned", "open") == "in-progress"
    assert load_tickets._map_status("open_unassigned", "open") == "open"


class TestUpserts:
  """DB upsert behavior tests."""

  def test_upsert_tickets_sanitizes_hours_and_timestamps(self) -> None:
    """Non-finite values are sanitized before SQL params are sent."""
    cursor = _DummyCursor()
    conn = _DummyConn(cursor)

    ticket = {
      "id": "hashicorp_terraform-1",
      "title": "Bug",
      "normalized_text": "normalized",
      "body": "raw",
      "embedding": [0.1] * load_tickets.EMBEDDING_DIM,
      "labels": "bug,triage",
      "issue_type": "closed",
      "state": "closed",
      "completion_hours_business": float("nan"),
      "created_at": float("nan"),
    }

    with patch(
      "training.etl.postload.load_tickets.psycopg2.connect",
      return_value=conn,
    ):
      count = load_tickets.upsert_tickets([ticket], dsn="postgresql://fake")

    assert count == 1
    assert len(cursor.executions) == 1
    _, params = cursor.executions[0]
    assert params[6] is None
    assert params[7] is None
    assert params[8] is None

  def test_upsert_assignments_handles_missing_and_unassigned(self) -> None:
    """Only assigned tickets with matching users are upserted."""
    cursor = _DummyCursor(rowcounts=[1, 0])
    conn = _DummyConn(cursor)

    tickets = [
      {
        "id": "t-unassigned",
        "assignee": None,
        "assigned_at": None,
        "created_at": "2026-01-01T00:00:00Z",
      },
      {
        "id": "t-assigned",
        "assignee": "alice",
        "assigned_at": "2026-01-02T00:00:00Z",
        "created_at": "2026-01-01T00:00:00Z",
      },
      {
        "id": "t-missing-user",
        "assignee": "ghost",
        "assigned_at": float("nan"),
        "created_at": "2026-01-03T00:00:00Z",
      },
    ]

    with patch(
      "training.etl.postload.load_tickets.psycopg2.connect",
      return_value=conn,
    ):
      upserted, missing = load_tickets.upsert_assignments(
        tickets,
        dsn="postgresql://fake",
      )

    assert upserted == 1
    assert missing == 1
    assert len(cursor.executions) == 2
    _, second_params = cursor.executions[1]
    assert second_params[1] == "2026-01-03T00:00:00Z"


class TestPipeline:
  """End-to-end orchestration tests with mocked dependencies."""

  def test_run_pipeline_orchestrates_steps(self) -> None:
    """Pipeline runs scrape -> transform -> ticket upsert -> assignment upsert."""
    calls: list[str] = []

    async def _fake_scrape(limit_per_state: int | None = None) -> list[dict]:
      assert limit_per_state == 10
      calls.append("scrape")
      return [{"id": "t1"}]

    def _fake_transform(records: list[dict]) -> list[dict]:
      assert records == [{"id": "t1"}]
      calls.append("transform")
      return [{"id": "t1", "assignee": None}]

    def _fake_upsert_tickets(records: list[dict], dsn: str | None = None) -> int:
      assert dsn == "postgresql://fake"
      assert records == [{"id": "t1", "assignee": None}]
      calls.append("tickets")
      return 1

    def _fake_upsert_assignments(
      records: list[dict],
      dsn: str | None = None,
    ) -> tuple[int, int]:
      assert dsn == "postgresql://fake"
      assert records == [{"id": "t1", "assignee": None}]
      calls.append("assignments")
      return (0, 0)

    with patch(
      "training.etl.postload.load_tickets.scrape_all_issues",
      _fake_scrape,
    ), patch(
      "training.etl.postload.load_tickets.transform_records",
      _fake_transform,
    ), patch(
      "training.etl.postload.load_tickets.upsert_tickets",
      _fake_upsert_tickets,
    ), patch(
      "training.etl.postload.load_tickets.upsert_assignments",
      _fake_upsert_assignments,
    ):
      result = asyncio.run(
        load_tickets.run_pipeline(dsn="postgresql://fake", limit_per_state=10)
      )

    assert result == 1
    assert calls == ["scrape", "transform", "tickets", "assignments"]
