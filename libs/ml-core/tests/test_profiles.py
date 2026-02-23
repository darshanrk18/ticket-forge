"""Tests for engineer profile updates."""

import numpy as np
import pytest
from ml_core.profiles import EngineerProfile, ProfileUpdater


class TestEngineerProfile:
  """Test cases for EngineerProfile model."""

  def test_create_profile(self) -> None:
    """Test creating an engineer profile."""
    embedding = np.random.rand(384)
    profile = EngineerProfile(
      engineer_id="ENG-001",
      embedding=embedding,
      keywords={"python": 5, "aws": 3},
    )

    assert profile.engineer_id == "ENG-001"
    assert profile.embedding.shape == (384,)
    assert profile.keywords == {"python": 5, "aws": 3}
    assert profile.tickets_completed == 0

  def test_to_dict_and_from_dict(self) -> None:
    """Test serialization and deserialization."""
    embedding = np.random.rand(384)
    profile = EngineerProfile(
      engineer_id="ENG-001",
      embedding=embedding,
      keywords={"python": 5},
    )

    # Convert to dict and back
    data = profile.to_dict()
    restored = EngineerProfile.from_dict(data)

    assert restored.engineer_id == profile.engineer_id
    np.testing.assert_array_equal(restored.embedding, profile.embedding)
    assert restored.keywords == profile.keywords


class TestProfileUpdater:
  """Test cases for ProfileUpdater."""

  @pytest.fixture
  def updater(self) -> ProfileUpdater:
    """Create a profile updater."""
    return ProfileUpdater(alpha=0.9)

  @pytest.fixture
  def engineer(self) -> EngineerProfile:
    """Create a sample engineer profile."""
    return EngineerProfile(
      engineer_id="ENG-001",
      embedding=np.ones(384),  # All 1s for easy testing
      keywords={"python": 5, "docker": 3},
    )

  def test_update_embedding_shape(
    self, updater: ProfileUpdater, engineer: EngineerProfile
  ) -> None:
    """Test that embedding maintains correct shape after update."""
    ticket_embedding = np.zeros(384)
    ticket_keywords = ["kubernetes", "aws"]

    updated = updater.update_on_ticket_completion(
      engineer, ticket_embedding, ticket_keywords
    )

    assert updated.embedding.shape == (384,)

  def test_update_embedding_values(
    self, updater: ProfileUpdater, engineer: EngineerProfile
  ) -> None:
    """Test that embedding is correctly weighted."""
    # Engineer has all 1s, ticket has all 0s
    ticket_embedding = np.zeros(384)
    ticket_keywords = []

    updated = updater.update_on_ticket_completion(
      engineer, ticket_embedding, ticket_keywords
    )

    # With alpha=0.9: new = 0.9*1 + 0.1*0 = 0.9
    expected = np.full(384, 0.9)
    np.testing.assert_array_almost_equal(updated.embedding, expected)

  def test_update_keywords_new(
    self, updater: ProfileUpdater, engineer: EngineerProfile
  ) -> None:
    """Test adding new keywords."""
    ticket_embedding = np.ones(384)
    ticket_keywords = ["kubernetes", "aws"]

    updated = updater.update_on_ticket_completion(
      engineer, ticket_embedding, ticket_keywords
    )

    assert updated.keywords["kubernetes"] == 1
    assert updated.keywords["aws"] == 1
    assert updated.keywords["python"] == 5  # Original unchanged

  def test_update_keywords_existing(
    self, updater: ProfileUpdater, engineer: EngineerProfile
  ) -> None:
    """Test incrementing existing keywords."""
    ticket_embedding = np.ones(384)
    ticket_keywords = ["python", "docker", "kubernetes"]

    updated = updater.update_on_ticket_completion(
      engineer, ticket_embedding, ticket_keywords
    )

    assert updated.keywords["python"] == 6  # 5 + 1
    assert updated.keywords["docker"] == 4  # 3 + 1
    assert updated.keywords["kubernetes"] == 1  # New

  def test_update_metadata(
    self, updater: ProfileUpdater, engineer: EngineerProfile
  ) -> None:
    """Test that metadata is updated."""
    ticket_embedding = np.ones(384)
    ticket_keywords = []

    assert engineer.tickets_completed == 0
    assert engineer.last_updated is None

    updated = updater.update_on_ticket_completion(
      engineer, ticket_embedding, ticket_keywords
    )

    assert updated.tickets_completed == 1
    assert updated.last_updated is not None

  def test_multiple_updates(
    self, updater: ProfileUpdater, engineer: EngineerProfile
  ) -> None:
    """Test multiple sequential updates."""
    ticket1_emb = np.zeros(384)
    ticket2_emb = np.full(384, 0.5)

    # First update
    updated1 = updater.update_on_ticket_completion(engineer, ticket1_emb, ["aws"])

    # Second update
    updated2 = updater.update_on_ticket_completion(
      updated1, ticket2_emb, ["aws", "kubernetes"]
    )

    assert updated2.tickets_completed == 2
    assert updated2.keywords["aws"] == 2  # Incremented twice
    assert updated2.keywords["kubernetes"] == 1

  def test_dimension_mismatch_raises_error(
    self, updater: ProfileUpdater, engineer: EngineerProfile
  ) -> None:
    """Test that mismatched dimensions raise error."""
    wrong_embedding = np.zeros(512)  # Wrong size!

    with pytest.raises(ValueError, match="dimension mismatch"):
      updater.update_on_ticket_completion(engineer, wrong_embedding, [])

  def test_get_decay_influence(self, updater: ProfileUpdater) -> None:
    """Test calculating resume influence over time."""
    # After 0 tickets: 100% resume
    assert updater.get_decay_influence(0) == 1.0

    # After 1 ticket: 90% resume
    assert abs(updater.get_decay_influence(1) - 0.9) < 0.001

    # After 10 tickets: ~35% resume
    assert abs(updater.get_decay_influence(10) - 0.349) < 0.001

    # After 50 tickets: ~0.5% resume
    assert updater.get_decay_influence(50) < 0.01

  def test_custom_alpha(self) -> None:
    """Test using custom alpha value."""
    updater = ProfileUpdater(alpha=0.8)  # Faster decay
    engineer = EngineerProfile(engineer_id="ENG-001", embedding=np.ones(384))
    ticket_emb = np.zeros(384)

    updated = updater.update_on_ticket_completion(engineer, ticket_emb, [])

    # With alpha=0.8: new = 0.8*1 + 0.2*0 = 0.8
    expected = np.full(384, 0.8)
    np.testing.assert_array_almost_equal(updated.embedding, expected)

  def test_invalid_alpha_raises_error(self) -> None:
    """Test that invalid alpha values raise error."""
    with pytest.raises(ValueError, match="Alpha must be between 0 and 1"):
      ProfileUpdater(alpha=1.5)

    with pytest.raises(ValueError, match="Alpha must be between 0 and 1"):
      ProfileUpdater(alpha=0.0)


class TestBuildProfileUpdateQuery:
  """Tests for ProfileUpdater.build_profile_update_query."""

  @pytest.fixture
  def updater(self) -> ProfileUpdater:
    """Create a ProfileUpdater with alpha=0.9."""
    return ProfileUpdater(alpha=0.9)

  def test_returns_sql_and_params(self, updater: ProfileUpdater) -> None:
    """Query and params tuple are returned."""
    sql, params = updater.build_profile_update_query(
      ticket_id="T-1", engineer_id=42, keywords_text="python docker"
    )
    assert isinstance(sql, str)
    assert isinstance(params, tuple)

  def test_sql_contains_update_and_decay(self, updater: ProfileUpdater) -> None:
    """SQL string should contain the UPDATE and both alpha terms."""
    sql, _ = updater.build_profile_update_query(
      ticket_id="T-1", engineer_id=42, keywords_text=""
    )
    assert "UPDATE users" in sql
    assert "profile_vector" in sql
    assert "ticket_vector" in sql
    assert "tickets_closed_count" in sql
    assert "skill_keywords" in sql

  def test_params_carry_alpha_values(self, updater: ProfileUpdater) -> None:
    """Params should carry alpha, 1-alpha, ticket_id, keywords, engineer_id."""
    sql, params = updater.build_profile_update_query(
      ticket_id="T-7", engineer_id=99, keywords_text="aws k8s"
    )
    assert params[0] == 0.9  # alpha
    assert params[1] == pytest.approx(0.1)  # 1 - alpha
    assert params[2] == "T-7"  # ticket_id
    assert params[3] == "aws k8s"  # keywords_text
    assert params[4] == 99  # engineer_id

  def test_alpha_consistency_with_numpy_update(self) -> None:
    """SQL and numpy paths must use the same alpha."""
    for alpha in (0.8, 0.95, 0.5):
      updater = ProfileUpdater(alpha=alpha)
      _, params = updater.build_profile_update_query(
        ticket_id="X", engineer_id=1, keywords_text=""
      )
      assert params[0] == alpha
      assert params[1] == pytest.approx(1.0 - alpha)
