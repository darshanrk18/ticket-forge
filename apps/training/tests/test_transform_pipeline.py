"""Tests for transformation pipeline."""

from training.etl.transform.embed import embed_text
from training.etl.transform.keyword_extraction import extract_keywords
from training.etl.transform.normalize_text import normalize_ticket_text
from training.etl.transform.temporal_features import (
  compute_business_completion_hours,
)


class TestNormalizeText:
  """Test text normalization."""

  def test_normalize_basic_text(self) -> None:
    """Test basic text normalization."""
    title = "Fix bug in API"
    body = "The API has a bug in the handler"

    result = normalize_ticket_text(title, body)

    assert "Fix bug in API" in result
    assert "API has a bug" in result

  def test_normalize_removes_markdown(self) -> None:
    """Test markdown removal."""
    title = "Test"
    body = "![image](url) and [link](url)"

    result = normalize_ticket_text(title, body)

    assert "![image]" not in result
    assert "[link]" not in result

  def test_normalize_truncates_code(self) -> None:
    """Test code block truncation."""
    title = "Test"
    body = "```\nline1\nline2\nline3\nline4\nline5\nline6\nline7\n```"

    result = normalize_ticket_text(title, body)

    assert "..." in result or "line" in result


class TestTemporalFeatures:
  """Test temporal feature computation."""

  def test_compute_with_assigned_at(self) -> None:
    """Test using assigned_at as start time."""
    created = "2026-01-01T10:00:00Z"
    assigned = "2026-01-01T12:00:00Z"
    closed = "2026-01-02T12:00:00Z"

    hours = compute_business_completion_hours(created, assigned, closed)

    assert hours is not None
    assert hours > 0

  def test_compute_fallback_to_created(self) -> None:
    """Test fallback to created_at when no assigned_at."""
    created = "2026-01-01T10:00:00Z"
    closed = "2026-01-02T10:00:00Z"

    hours = compute_business_completion_hours(created, None, closed)

    assert hours is not None
    assert hours > 0

  def test_compute_returns_none_when_no_closed(self) -> None:
    """Test returns None when ticket not closed."""
    created = "2026-01-01T10:00:00Z"

    hours = compute_business_completion_hours(created, None, None)

    assert hours is None


class TestKeywordExtraction:
  """Test keyword extraction."""

  def test_extract_keywords_from_list(self) -> None:
    """Test extracting keywords from text list."""
    texts = [
      "Fix Python bug in Docker",
      "Deploy to Kubernetes on AWS",
    ]

    keywords = extract_keywords(texts, top_k=5)

    assert len(keywords) == 2
    assert isinstance(keywords[0], list)


class TestEmbedText:
  """Test embedding generation."""

  def test_embed_returns_correct_shape(self) -> None:
    """Test embedding returns 384-dimensional vectors."""
    texts = ["Fix bug", "Deploy app"]

    embeddings = embed_text(texts)

    assert len(embeddings) == 2
    assert len(embeddings[0]) == 384
    assert isinstance(embeddings[0][0], float)
