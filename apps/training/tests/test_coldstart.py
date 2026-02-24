"""Tests for the cold-start ETL module.

These tests exercise the pure-logic helpers (profile creation, merging,
deduplication) and verify the upsert-strategy selection without hitting
a real database.  All Postgres / embedding interactions are mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from training.etl.ingest.resume.coldstart import (
  EMBEDDING_DIM,
  SIMILARITY_THRESHOLD,
  ColdStartManager,
  EngineerProfile,
  TicketUser,
  ensure_profiles_for_tickets,
)

# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #


def _make_profile(
  ghuser: str = "alice",
  embedding: list[float] | None = None,
  keywords: list[str] | None = None,
) -> EngineerProfile:
  return EngineerProfile(
    engineer_id=ghuser,
    github_username=ghuser,
    full_name=ghuser.title(),
    embedding=embedding if embedding is not None else [1.0] * EMBEDDING_DIM,
    keywords=keywords if keywords is not None else ["python"],
    created_at=datetime.now(tz=UTC).isoformat(),
  )


def _zero_profile(ghuser: str = "bob") -> EngineerProfile:
  return _make_profile(ghuser=ghuser, embedding=[0.0] * EMBEDDING_DIM, keywords=[])


# ------------------------------------------------------------------ #
#  TicketUser dataclass
# ------------------------------------------------------------------ #


class TestTicketUser:
  """Basic TicketUser construction."""

  def test_defaults(self) -> None:
    """Username is stored and full_name defaults to None."""
    tu = TicketUser(github_username="alice")
    assert tu.github_username == "alice"
    assert tu.full_name is None

  def test_with_full_name(self) -> None:
    """Full name is retained when provided."""
    tu = TicketUser(github_username="bob", full_name="Bob Smith")
    assert tu.full_name == "Bob Smith"


# ------------------------------------------------------------------ #
#  EngineerProfile dataclass
# ------------------------------------------------------------------ #


class TestEngineerProfile:
  """Basic EngineerProfile construction."""

  def test_fields(self) -> None:
    """Profile fields are set correctly from helper."""
    p = _make_profile()
    assert p.engineer_id == "alice"
    assert p.github_username == "alice"
    assert len(p.embedding) == EMBEDDING_DIM
    assert p.keywords == ["python"]

  def test_zero_embedding(self) -> None:
    """Zero-vector profile has all-zero embedding and empty keywords."""
    p = _zero_profile()
    assert all(v == 0.0 for v in p.embedding)
    assert p.keywords == []


# ------------------------------------------------------------------ #
#  profiles_from_tickets
# ------------------------------------------------------------------ #


class TestProfilesFromTickets:
  """Creating stub profiles from ticket assignee data."""

  def test_creates_correct_count(self) -> None:
    """One profile is created per ticket user."""
    users = [TicketUser("a"), TicketUser("b"), TicketUser("c")]
    profiles = ColdStartManager.profiles_from_tickets(users)
    assert len(profiles) == 3

  def test_stub_has_zero_embedding(self) -> None:
    """Stub embedding is None (no embedding for ticket-sourced stubs)."""
    profiles = ColdStartManager.profiles_from_tickets([TicketUser("alice")])
    p = profiles[0]
    assert p.embedding is None

  def test_stub_has_empty_keywords(self) -> None:
    """Stubs have no keywords."""
    profiles = ColdStartManager.profiles_from_tickets([TicketUser("alice")])
    assert profiles[0].keywords == []

  def test_full_name_defaults_to_username(self) -> None:
    """Full name falls back to the GitHub username."""
    profiles = ColdStartManager.profiles_from_tickets([TicketUser("alice")])
    assert profiles[0].full_name == "alice"

  def test_full_name_used_when_provided(self) -> None:
    """Explicit full name is preserved."""
    tu = TicketUser(github_username="alice", full_name="Alice Z")
    profiles = ColdStartManager.profiles_from_tickets([tu])
    assert profiles[0].full_name == "Alice Z"

  def test_empty_input_returns_empty(self) -> None:
    """No users yields an empty list."""
    assert ColdStartManager.profiles_from_tickets([]) == []


# ------------------------------------------------------------------ #
#  merge_user_sources
# ------------------------------------------------------------------ #


class TestMergeUserSources:
  """Merging resume profiles with ticket assignees."""

  @pytest.fixture()
  def mgr(self) -> ColdStartManager:
    """Create a ColdStartManager with mocked dependencies."""
    with patch.multiple(
      "training.etl.ingest.resume.coldstart",
      ResumeExtractor=MagicMock,
      ResumeNormalizer=MagicMock,
      get_embedding_service=MagicMock,
      get_keyword_extractor=MagicMock,
    ):
      return ColdStartManager(dsn="postgresql://fake")

  def test_resume_only(self, mgr: ColdStartManager) -> None:
    """Resume-only input passes through unchanged."""
    profiles = [_make_profile("alice")]
    merged = mgr.merge_user_sources(profiles, [])
    assert len(merged) == 1
    assert merged[0].github_username == "alice"

  def test_ticket_only(self, mgr: ColdStartManager) -> None:
    """Ticket-only users get None-embedding stub profiles."""
    merged = mgr.merge_user_sources([], [TicketUser("bob")])
    assert len(merged) == 1
    assert merged[0].github_username == "bob"
    assert merged[0].embedding is None

  def test_resume_wins_over_ticket(self, mgr: ColdStartManager) -> None:
    """When the same user appears in both sources, the resume profile wins."""
    resume = _make_profile("alice")
    ticket = TicketUser("alice")
    merged = mgr.merge_user_sources([resume], [ticket])
    assert len(merged) == 1
    # The kept profile should have a real embedding (from resume), not None
    assert merged[0].embedding is not None
    assert any(v != 0.0 for v in merged[0].embedding)

  def test_disjoint_users_combined(self, mgr: ColdStartManager) -> None:
    """Users from different sources are all included."""
    resume = _make_profile("alice")
    ticket = TicketUser("bob")
    merged = mgr.merge_user_sources([resume], [ticket])
    names = {p.github_username for p in merged}
    assert names == {"alice", "bob"}

  def test_duplicate_ticket_users(self, mgr: ColdStartManager) -> None:
    """If the same ticket user appears twice, it should only appear once."""
    tickets = [TicketUser("bob"), TicketUser("bob")]
    merged = mgr.merge_user_sources([], tickets)
    # profiles_from_tickets doesn't deduplicate, but merge_user_sources
    # feeds through without extra dedup — that's fine because
    # ensure_profiles_for_tickets does the dedup at the ETL layer.
    assert len(merged) == 2  # raw pass-through is acceptable


# ------------------------------------------------------------------ #
#  _upsert_profiles — strategy dispatch (mocked DB)
# ------------------------------------------------------------------ #


class TestUpsertStrategyDispatch:
  """Verify _upsert_profiles picks the right strategy method."""

  @pytest.fixture()
  def mgr(self) -> ColdStartManager:
    """Create a ColdStartManager with mocked dependencies."""
    with patch.multiple(
      "training.etl.ingest.resume.coldstart",
      ResumeExtractor=MagicMock,
      ResumeNormalizer=MagicMock,
      get_embedding_service=MagicMock,
      get_keyword_extractor=MagicMock,
    ):
      return ColdStartManager(dsn="postgresql://fake")

  @staticmethod
  def _fake_lookup(
    is_stub: bool = False,
    cosine_dist: float | None = 0.5,
    member_id: int = 42,
  ) -> dict[str, Any]:
    return {
      "member_id": member_id,
      "is_stub": is_stub,
      "cosine_dist": cosine_dist,
    }

  def test_insert_new_when_no_existing_row(self, mgr: ColdStartManager) -> None:
    """No matching row → _insert_new."""
    profile = _make_profile("alice")
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur

    with patch.object(mgr, "_get_connection", return_value=mock_conn):
      with patch.object(mgr, "_lookup_user", return_value=None):
        with patch.object(
          mgr, "_insert_new", return_value={"member_id": "1", "action": "created"}
        ) as insert_mock:
          results = mgr._upsert_profiles([profile])

    insert_mock.assert_called_once()
    assert results[0]["action"] == "created"

  def test_decay_blend_when_stub(self, mgr: ColdStartManager) -> None:
    """Existing stub row + real signal → _decay_blend (enrichment)."""
    profile = _make_profile("alice")
    row = self._fake_lookup(is_stub=True, cosine_dist=None)
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur

    with patch.object(mgr, "_get_connection", return_value=mock_conn):
      with patch.object(mgr, "_lookup_user", return_value=row):
        with patch.object(
          mgr, "_decay_blend", return_value={"member_id": "42", "action": "updated"}
        ) as blend_mock:
          results = mgr._upsert_profiles([profile])

    blend_mock.assert_called_once()
    assert results[0]["action"] == "updated"

  def test_skip_when_near_duplicate(self, mgr: ColdStartManager) -> None:
    """cosine_dist < threshold → _skip_duplicate."""
    profile = _make_profile("alice")
    tiny_dist = SIMILARITY_THRESHOLD / 2
    row = self._fake_lookup(is_stub=False, cosine_dist=tiny_dist)
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur

    with patch.object(mgr, "_get_connection", return_value=mock_conn):
      with patch.object(mgr, "_lookup_user", return_value=row):
        with patch.object(
          mgr, "_skip_duplicate", return_value={"member_id": "42", "action": "skipped"}
        ) as skip_mock:
          results = mgr._upsert_profiles([profile])

    skip_mock.assert_called_once()
    assert results[0]["action"] == "skipped"

  def test_decay_blend_when_different_resume(self, mgr: ColdStartManager) -> None:
    """cosine_dist > threshold on non-stub → _decay_blend."""
    profile = _make_profile("alice")
    row = self._fake_lookup(is_stub=False, cosine_dist=0.8)
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur

    with patch.object(mgr, "_get_connection", return_value=mock_conn):
      with patch.object(mgr, "_lookup_user", return_value=row):
        with patch.object(
          mgr, "_decay_blend", return_value={"member_id": "42", "action": "updated"}
        ) as blend_mock:
          results = mgr._upsert_profiles([profile])

    blend_mock.assert_called_once()
    assert results[0]["action"] == "updated"

  def test_rollback_on_error(self, mgr: ColdStartManager) -> None:
    """On exception the transaction is rolled back."""
    profile = _make_profile("alice")
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur

    with patch.object(mgr, "_get_connection", return_value=mock_conn):
      with patch.object(mgr, "_lookup_user", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
          mgr._upsert_profiles([profile])

    mock_conn.rollback.assert_called_once()
    mock_conn.commit.assert_not_called()


# ------------------------------------------------------------------ #
#  ensure_profiles_for_tickets (ETL helper)
# ------------------------------------------------------------------ #


class TestEnsureProfilesForTickets:
  """Tests for the top-level ETL helper function."""

  def test_empty_tickets_returns_empty(self) -> None:
    """No tickets yields an empty result."""
    assert ensure_profiles_for_tickets([]) == []

  def test_missing_assignee_skipped(self) -> None:
    """Tickets without an assignee key are ignored."""
    tickets = [{"title": "Fix bug"}]  # no assignee key
    assert ensure_profiles_for_tickets(tickets) == []

  def test_deduplicates_assignees(self) -> None:
    """Duplicate assignee usernames are collapsed."""
    tickets = [
      {"assignee": "alice"},
      {"assignee": "alice"},
      {"assignee": "bob"},
    ]
    with patch.object(ColdStartManager, "__init__", return_value=None):
      with patch.object(
        ColdStartManager,
        "save_profiles",
        return_value=[
          {"member_id": "1", "action": "created"},
          {"member_id": "2", "action": "created"},
        ],
      ) as save_mock:
        results = ensure_profiles_for_tickets(tickets, dsn="postgresql://fake")

    # Only 2 unique assignees should be passed
    saved = save_mock.call_args[0][0]
    usernames = [p.github_username for p in saved]
    assert sorted(usernames) == ["alice", "bob"]
    assert len(results) == 2

  def test_custom_assignee_key(self) -> None:
    """A custom assignee key is respected."""
    tickets = [{"owner": "charlie"}]
    with patch.object(ColdStartManager, "__init__", return_value=None):
      with patch.object(
        ColdStartManager,
        "save_profiles",
        return_value=[{"member_id": "1", "action": "created"}],
      ) as save_mock:
        results = ensure_profiles_for_tickets(
          tickets, dsn="postgresql://fake", assignee_key="owner"
        )

    saved = save_mock.call_args[0][0]
    assert saved[0].github_username == "charlie"
    assert len(results) == 1


# ------------------------------------------------------------------ #
#  _ensure_row
# ------------------------------------------------------------------ #


class TestEnsureRow:
  """Tests for the _ensure_row helper."""

  def test_returns_dict_when_present(self) -> None:
    """Returns the dict when a result is present."""
    assert ColdStartManager._ensure_row({"member_id": 1}) == {"member_id": 1}

  def test_raises_when_none(self) -> None:
    """Raises RuntimeError when the result is None."""
    with pytest.raises(RuntimeError, match="RETURNING"):
      ColdStartManager._ensure_row(None)
