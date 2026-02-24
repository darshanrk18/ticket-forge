"""Tests for the ticket replay post-load module.

Exercises the replay logic by mocking the Postgres connection so no
real database is required.  Validates chronological ordering, the
Experience Decay SQL parameters, atomic commit semantics, and
edge cases (no tickets, alpha validation).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from training.etl.postload.replay_tickets import (
  DEFAULT_ALPHA,
  ClosedTicketAssignment,
  TicketReplayer,
  main,
)

# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #


_ASSIGNMENT_DEFAULTS: dict[str, object] = {
  "ticket_id": "T-1",
  "title": "Fix the widget",
  "description": "The widget was broken due to python error",
  "engineer_id": 42,
  "github_username": "alice",
  "closed_at": "2025-06-01T12:00:00+00:00",
}


def _make_assignment(**overrides: object) -> ClosedTicketAssignment:
  """Build a ``ClosedTicketAssignment`` with sensible defaults."""
  fields = {**_ASSIGNMENT_DEFAULTS, **overrides}
  return ClosedTicketAssignment(**fields)  # type: ignore[arg-type]


DB_ROW_KEYS = [
  "ticket_id",
  "title",
  "description",
  "engineer_id",
  "github_username",
  "closed_at",
]


def _row_dict(assignment: ClosedTicketAssignment) -> dict:
  """Convert a ClosedTicketAssignment to a dict like RealDictCursor returns."""
  return {
    "ticket_id": assignment.ticket_id,
    "title": assignment.title,
    "description": assignment.description,
    "engineer_id": assignment.engineer_id,
    "github_username": assignment.github_username,
    "closed_at": assignment.closed_at,
  }


# ------------------------------------------------------------------ #
#  Construction
# ------------------------------------------------------------------ #


class TestTicketReplayerInit:
  """Tests for TicketReplayer.__init__."""

  @patch.dict("os.environ", {"DATABASE_URL": "postgresql://test:test@localhost/test"})
  def test_default_dsn_from_env(self) -> None:
    """DSN is read from DATABASE_URL when not passed explicitly."""
    replayer = TicketReplayer()
    assert replayer.dsn == "postgresql://test:test@localhost/test"

  def test_explicit_dsn(self) -> None:
    """Explicit dsn kwarg takes precedence."""
    replayer = TicketReplayer(dsn="postgresql://a:b@c/d")
    assert replayer.dsn == "postgresql://a:b@c/d"

  @patch.dict("os.environ", {}, clear=True)
  def test_missing_dsn_raises(self) -> None:
    """RuntimeError when no DSN is available."""
    with pytest.raises(RuntimeError, match="No Postgres DSN"):
      TicketReplayer()

  def test_alpha_out_of_range_raises(self) -> None:
    """ValueError when alpha is not in (0, 1)."""
    with pytest.raises(ValueError, match="Alpha must be between"):
      TicketReplayer(dsn="postgresql://x", alpha=0.0)
    with pytest.raises(ValueError, match="Alpha must be between"):
      TicketReplayer(dsn="postgresql://x", alpha=1.0)
    with pytest.raises(ValueError, match="Alpha must be between"):
      TicketReplayer(dsn="postgresql://x", alpha=-0.5)

  def test_valid_alpha(self) -> None:
    """Custom alpha is stored on the instance."""
    r = TicketReplayer(dsn="postgresql://x", alpha=0.8)
    assert r.alpha == 0.8


# ------------------------------------------------------------------ #
#  Replay — no tickets
# ------------------------------------------------------------------ #


class TestReplayEmpty:
  """Edge case: no closed ticket assignments exist."""

  @patch("training.etl.postload.replay_tickets.psycopg2")
  def test_replay_returns_zero_when_no_tickets(self, mock_pg: MagicMock) -> None:
    """DB returns no rows for the given IDs."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value = mock_cursor
    mock_pg.connect.return_value = mock_conn

    replayer = TicketReplayer(dsn="postgresql://x")
    assert replayer.replay(["T-99"]) == 0

    # Should NOT have called commit (nothing to apply)
    mock_conn.commit.assert_not_called()

  def test_replay_returns_zero_for_empty_list(self) -> None:
    """Empty ticket list short-circuits without connecting."""
    replayer = TicketReplayer(dsn="postgresql://x")
    assert replayer.replay([]) == 0


# ------------------------------------------------------------------ #
#  Replay — single ticket
# ------------------------------------------------------------------ #


class TestReplaySingle:
  """One closed ticket assigned to one engineer."""

  @patch("training.etl.postload.replay_tickets.psycopg2")
  def test_single_ticket_applies_decay(self, mock_pg: MagicMock) -> None:
    """One ticket produces one UPDATE with correct alpha params."""
    assignment = _make_assignment()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    # First fetchall returns the ticket list
    mock_cursor.fetchall.return_value = [_row_dict(assignment)]
    mock_conn.cursor.return_value = mock_cursor
    mock_pg.connect.return_value = mock_conn

    alpha = 0.9
    replayer = TicketReplayer(dsn="postgresql://x", alpha=alpha)
    count = replayer.replay(["T-1"])

    assert count == 1

    # The UPDATE was executed once
    update_calls = [
      c for c in mock_cursor.execute.call_args_list if "UPDATE users" in str(c)
    ]
    assert len(update_calls) == 1

    # Verify the alpha / (1-alpha) / ticket_id values passed to SQL
    sql_args = update_calls[0][0][1]  # positional args tuple
    assert sql_args[0] == alpha  # alpha
    assert sql_args[1] == pytest.approx(1.0 - alpha)  # 1 - alpha
    assert sql_args[2] == assignment.ticket_id  # ticket_id
    assert sql_args[4] == assignment.engineer_id

    # single atomic commit after all updates
    assert mock_conn.commit.call_count == 1


# ------------------------------------------------------------------ #
#  Replay — multiple tickets (chronological ordering)
# ------------------------------------------------------------------ #


class TestReplayMultiple:
  """Multiple tickets processed in the order the DB returns them."""

  @patch("training.etl.postload.replay_tickets.psycopg2")
  def test_multiple_tickets_processed_in_order(self, mock_pg: MagicMock) -> None:
    """Tickets are replayed in the chronological order returned by the DB."""
    a1 = _make_assignment(ticket_id="T-1", closed_at="2025-01-01T00:00:00+00:00")
    a2 = _make_assignment(
      ticket_id="T-2",
      engineer_id=99,
      github_username="bob",
      closed_at="2025-03-01T00:00:00+00:00",
    )
    a3 = _make_assignment(ticket_id="T-3", closed_at="2025-06-01T00:00:00+00:00")

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
      _row_dict(a1),
      _row_dict(a2),
      _row_dict(a3),
    ]
    mock_conn.cursor.return_value = mock_cursor
    mock_pg.connect.return_value = mock_conn

    replayer = TicketReplayer(dsn="postgresql://x")
    count = replayer.replay(["T-1", "T-2", "T-3"])

    assert count == 3
    # Single atomic commit for all tickets
    assert mock_conn.commit.call_count == 1

    # Verify ticket_ids were passed in chronological order
    update_calls = [
      c for c in mock_cursor.execute.call_args_list if "UPDATE users" in str(c)
    ]
    ticket_ids_in_order = [c[0][1][2] for c in update_calls]
    assert ticket_ids_in_order == ["T-1", "T-2", "T-3"]


# ------------------------------------------------------------------ #
#  Replay — DB error triggers rollback
# ------------------------------------------------------------------ #


class TestReplayError:
  """DB errors should cause rollback and re-raise."""

  @patch("training.etl.postload.replay_tickets.psycopg2")
  def test_db_error_rolls_back(self, mock_pg: MagicMock) -> None:
    """A DB exception triggers rollback and re-raise."""
    assignment = _make_assignment()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [_row_dict(assignment)]
    # Make the UPDATE blow up
    mock_cursor.execute.side_effect = [
      None,  # first call is the SELECT (fetch assignments)
      Exception("boom"),  # second call is the UPDATE
    ]
    mock_conn.cursor.return_value = mock_cursor
    mock_pg.connect.return_value = mock_conn

    replayer = TicketReplayer(dsn="postgresql://x")
    with pytest.raises(Exception, match="boom"):
      replayer.replay(["T-1"])

    mock_conn.rollback.assert_called_once()
    mock_conn.close.assert_called_once()


# ------------------------------------------------------------------ #
#  SQL query shape
# ------------------------------------------------------------------ #


class TestFetchQuery:
  """Verify the fetch query includes the right tables and ordering."""

  @patch("training.etl.postload.replay_tickets.psycopg2")
  def test_fetch_query_joins_and_orders(self, mock_pg: MagicMock) -> None:
    """SELECT joins assignments and users, filters by ANY, orders ASC."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value = mock_cursor
    mock_pg.connect.return_value = mock_conn

    replayer = TicketReplayer(dsn="postgresql://x")
    replayer.replay(["T-1", "T-2"])

    select_call = mock_cursor.execute.call_args_list[0]
    sql = select_call[0][0]
    assert "JOIN assignments" in sql
    assert "JOIN users" in sql
    assert "ANY" in sql
    assert "ORDER BY" in sql
    assert "ASC" in sql

    # Verify the ticket IDs were passed as the parameter
    sql_args = select_call[0][1]
    assert sql_args == (["T-1", "T-2"],)


# ------------------------------------------------------------------ #
#  Keyword extraction integration
# ------------------------------------------------------------------ #


class TestKeywordExtraction:
  """Keywords from ticket text are passed to the UPDATE."""

  @patch("training.etl.postload.replay_tickets.psycopg2")
  def test_keywords_extracted_from_ticket_text(self, mock_pg: MagicMock) -> None:
    """Keywords from title+description are passed to the UPDATE."""
    assignment = _make_assignment(
      title="Upgrade Python to 3.12",
      description="Migrate the Docker containers to use Python 3.12",
    )
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [_row_dict(assignment)]
    mock_conn.cursor.return_value = mock_cursor
    mock_pg.connect.return_value = mock_conn

    replayer = TicketReplayer(dsn="postgresql://x")
    replayer.replay(["T-1"])

    update_calls = [
      c for c in mock_cursor.execute.call_args_list if "UPDATE users" in str(c)
    ]
    assert len(update_calls) == 1
    keywords_arg = update_calls[0][0][1][3]  # 4th param is keywords_text
    # Should contain extracted keywords (at minimum "python" and "docker")
    kw_lower = keywords_arg.lower()
    assert "python" in kw_lower or "docker" in kw_lower


# ------------------------------------------------------------------ #
#  CLI entry-point
# ------------------------------------------------------------------ #


class TestCLI:
  """Tests for the ``main()`` CLI wrapper."""

  @patch("training.etl.postload.replay_tickets.TicketReplayer")
  def test_main_with_ticket_ids(self, mock_cls: MagicMock) -> None:
    """Positional ticket IDs are forwarded to replay()."""
    mock_instance = MagicMock()
    mock_instance.replay.return_value = 5
    mock_cls.return_value = mock_instance

    main(["--dsn", "postgresql://x", "T-1", "T-2"])

    mock_cls.assert_called_once_with(dsn="postgresql://x", alpha=DEFAULT_ALPHA)
    mock_instance.replay.assert_called_once_with(["T-1", "T-2"])

  @patch("training.etl.postload.replay_tickets.TicketReplayer")
  def test_main_custom_alpha(self, mock_cls: MagicMock) -> None:
    """--alpha is forwarded to the TicketReplayer constructor."""
    mock_instance = MagicMock()
    mock_instance.replay.return_value = 2
    mock_cls.return_value = mock_instance

    main(["--dsn", "postgresql://x", "--alpha", "0.8", "T-1"])

    mock_cls.assert_called_once_with(dsn="postgresql://x", alpha=0.8)
    mock_instance.replay.assert_called_once_with(["T-1"])

  @patch("training.etl.postload.replay_tickets.TicketReplayer")
  def test_main_zero_count_message(
    self, mock_cls: MagicMock, capsys: pytest.CaptureFixture
  ) -> None:
    """Zero-count replay prints 'nothing to replay'."""
    mock_instance = MagicMock()
    mock_instance.replay.return_value = 0
    mock_cls.return_value = mock_instance

    main(["--dsn", "postgresql://x", "T-1"])

    captured = capsys.readouterr()
    assert "nothing to replay" in captured.out.lower()

  @patch("training.etl.postload.replay_tickets.TicketReplayer")
  def test_main_from_file(self, mock_cls: MagicMock, tmp_path: Path) -> None:
    """--file reads ticket IDs from a text file."""
    mock_instance = MagicMock()
    mock_instance.replay.return_value = 3
    mock_cls.return_value = mock_instance

    id_file = tmp_path / "ids.txt"
    id_file.write_text("T-10\nT-20\nT-30\n")

    main(["--dsn", "postgresql://x", "--file", str(id_file)])

    mock_instance.replay.assert_called_once_with(["T-10", "T-20", "T-30"])

  def test_main_no_tickets_errors(self) -> None:
    """CLI errors when no ticket IDs are provided."""
    with pytest.raises(SystemExit):
      main(["--dsn", "postgresql://x"])
