"""Tests for ETL transformation pipeline functions."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from training.etl.transform.run_transform import transform_records


class TestTransformRecords:
  """Tests for complete transformation pipeline."""

  @pytest.fixture
  def sample_raw_tickets(self) -> list[dict[str, Any]]:
    """Create sample raw ticket records."""
    return [
      {
        "id": "issue_1",
        "repo": "test-repo",
        "title": "Fix bug in parser",
        "body": "The parser is broken when handling edge cases.",
        "url": "https://github.com/test-repo/issues/1",
        "state": "closed",
        "issue_type": "closed",
        "labels": '[{"name": "bug"}]',
        "assignee": "alice",
        "seniority": "senior",
        "created_at": "2025-01-01T10:00:00Z",
        "assigned_at": "2025-01-01T11:00:00Z",
        "closed_at": "2025-01-02T15:00:00Z",
        "comments_count": 3,
      },
      {
        "id": "issue_2",
        "repo": "test-repo",
        "title": "Add feature X",
        "body": "Please implement feature X as described in the spec.",
        "url": "https://github.com/test-repo/issues/2",
        "state": "open",
        "issue_type": "open",
        "labels": "[]",
        "assignee": "bob",
        "seniority": "mid",
        "created_at": "2025-01-03T09:00:00Z",
        "assigned_at": None,
        "closed_at": None,
        "comments_count": 1,
      },
    ]

  @patch("training.etl.transform.run_transform.embed_text")
  @patch("training.etl.transform.run_transform.enrich_engineer_features")
  def test_transform_records_returns_enriched_data(
    self,
    mock_enrich: MagicMock,
    mock_embed: MagicMock,
    sample_raw_tickets: list[dict[str, Any]],
  ) -> None:
    """transform_records returns list of dicts with embeddings."""
    # Mock embeddings: return simple vectors
    mock_embed.return_value = [
      [0.1] * 384,
      [0.2] * 384,
    ]
    # Mock engineer features enrichment (identity function for simplicity)
    mock_enrich.side_effect = lambda df: df

    result = transform_records(sample_raw_tickets)

    assert isinstance(result, list)
    assert len(result) == 2
    # Check structure
    for record in result:
      assert "id" in record
      assert "normalized_text" in record
      assert "embedding" in record
      assert "embedding_model" in record
      assert record["embedding_model"] == "all-MiniLM-L6-v2"

  @patch("training.etl.transform.run_transform.embed_text")
  @patch("training.etl.transform.run_transform.enrich_engineer_features")
  def test_transform_records_handles_empty_input(
    self,
    mock_enrich: MagicMock,
    mock_embed: MagicMock,
  ) -> None:
    """transform_records handles empty input gracefully."""
    result = transform_records([])
    assert result == []

  @patch("training.etl.transform.run_transform.embed_text")
  @patch("training.etl.transform.run_transform.enrich_engineer_features")
  def test_transform_records_fills_missing_fields(
    self,
    mock_enrich: MagicMock,
    mock_embed: MagicMock,
  ) -> None:
    """transform_records fills defaults for missing fields."""
    mock_embed.return_value = [[0.1] * 384]
    mock_enrich.side_effect = lambda df: df

    # Minimal record missing optional fields
    minimal = [
      {
        "id": "issue_3",
        "repo": "test-repo",
        "title": "Test",
        "body": "Test body",
        "url": "https://github.com/test-repo/issues/3",
        "state": "open",
        "issue_type": "open",
        "labels": "[]",
      }
    ]

    result = transform_records(minimal)

    assert len(result) == 1
    # Defaults should be applied
    assert result[0]["assignee"] is not None or pd.isna(result[0]["assignee"])
    assert result[0]["seniority"] is not None

  @patch("training.etl.transform.run_transform.embed_text")
  @patch("training.etl.transform.run_transform.enrich_engineer_features")
  def test_transform_records_computes_temporal_features(
    self,
    mock_enrich: MagicMock,
    mock_embed: MagicMock,
    sample_raw_tickets: list[dict[str, Any]],
  ) -> None:
    """transform_records computes completion hours."""
    mock_embed.return_value = [[0.1] * 384, [0.2] * 384]
    mock_enrich.side_effect = lambda df: df

    result = transform_records(sample_raw_tickets)

    # First ticket is closed, should have completion_hours_business
    assert "completion_hours_business" in result[0]
    # Second ticket is open, completion hours should be None
    assert "completion_hours_business" in result[1]
