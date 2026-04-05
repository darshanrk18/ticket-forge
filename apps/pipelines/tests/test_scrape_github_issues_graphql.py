"""Tests for GitHub issue scraper."""

from pipelines.etl.ingest.scrape_github_issues_improved import build_query


class TestGraphQLQueryBuilder:
  """Test cases for GraphQL query building."""

  def test_build_query_without_cursor(self) -> None:
    """Test building GraphQL query without pagination cursor."""
    query_dict = build_query("hashicorp", "terraform", "CLOSED", None)

    assert "query" in query_dict
    query = query_dict["query"]

    assert "hashicorp" in query
    assert "terraform" in query
    assert "CLOSED" in query
    assert "after:" not in query

  def test_build_query_with_cursor(self) -> None:
    """Test building GraphQL query with pagination cursor."""
    cursor = "test_cursor_123"
    query_dict = build_query("ansible", "ansible", "OPEN", cursor)

    query = query_dict["query"]

    assert "ansible" in query
    assert "OPEN" in query
    assert f'after: "{cursor}"' in query

  def test_query_includes_assignment_timeline(self) -> None:
    """Test that query includes assignment event tracking."""
    query_dict = build_query("test", "repo", "CLOSED", None)
    query = query_dict["query"]

    assert "timelineItems" in query
    assert "ASSIGNED_EVENT" in query

  def test_query_includes_all_required_fields(self) -> None:
    """Test that query requests all required fields."""
    query_dict = build_query("test", "repo", "CLOSED", None)
    query = query_dict["query"]

    required = [
      "number",
      "title",
      "body",
      "state",
      "createdAt",
      "closedAt",
      "assignees",
      "labels",
      "comments",
    ]

    for field in required:
      assert field in query, f"Missing field: {field}"
