"""Unit tests for hybrid retrieval query builders."""

from __future__ import annotations

from ml_core.retrieval.hybrid_retrieval import (
  build_hybrid_rrf_engineer_query,
  build_hybrid_rrf_engineer_query_from_ticket_text,
  vector_to_pgvector_text,
)


def test_vector_to_pgvector_text_dimension_mismatch() -> None:
  """Reject vectors with the wrong dimensionality."""
  try:
    vector_to_pgvector_text([0.0, 1.0], dim=384)
  except ValueError as e:
    assert "Expected embedding length 384" in str(e)
  else:
    msg = "Expected ValueError for wrong vector dimensionality"
    raise AssertionError(msg)


def test_vector_to_pgvector_text_serialization_format() -> None:
  """Validate pgvector literal formatting."""
  vec = [0.0] * 384
  text = vector_to_pgvector_text(vec, dim=384)
  assert text.startswith("[")
  assert text.endswith("]")

  inner = text[1:-1]
  # Split may produce a single element if formatting changes; keep it strict.
  parts = inner.split(",")
  assert len(parts) == 384


def test_build_hybrid_rrf_engineer_query_structure_and_params() -> None:
  """SQL should include hybrid components and params should match expectations."""
  vec = [0.0] * 384
  sql, params = build_hybrid_rrf_engineer_query(
    ticket_vector=vec,
    keyword_query_text="EKS Ingress",
    semantic_limit=10,
    lexical_limit=12,
    result_limit=5,
    rrf_k=60,
  )

  assert "WITH semantic_results AS" in sql
  assert "lexical_results AS" in sql
  assert "FULL OUTER JOIN lexical_results" in sql
  assert "rrf_score" in sql
  assert "ORDER BY rrf_score DESC" in sql

  # Params are:
  # 1) vector text
  # 2) semantic_limit
  # 3) keyword_query_text
  # 4) lexical_limit
  # 5) rrf_k
  # 6) missing_rank for semantic
  # 7) rrf_k
  # 8) missing_rank for lexical
  # 9) result_limit
  assert len(params) == 9

  vector_text = params[0]
  assert isinstance(vector_text, str)
  assert vector_text.startswith("[") and vector_text.endswith("]")
  inner = vector_text[1:-1]
  assert len(inner.split(",")) == 384

  assert params[1] == 10
  assert params[2] == "EKS Ingress"
  assert params[3] == 12

  missing_rank_expected = max(10, 12) + 1
  assert params[4] == 60
  assert params[5] == missing_rank_expected
  assert params[6] == 60
  assert params[7] == missing_rank_expected
  assert params[8] == 5


class _StubEmbeddingService:
  """Test stub for embedding service."""

  def __init__(self, dim: int) -> None:
    self._dim = dim

  def embed_text(self, text: str) -> list[float]:
    # Deterministic vector for tests; content of text is irrelevant.
    return [0.0] * self._dim


class _StubKeywordExtractor:
  """Test stub for keyword extractor."""

  def __init__(self, keywords: list[str]) -> None:
    self._keywords = keywords

  def extract(self, text: str, top_n: int | None = None) -> list[str]:
    _ = text
    _ = top_n
    return self._keywords


def test_build_hybrid_rrf_engineer_query_from_ticket_text_uses_ml_services() -> None:
  """Wrapper should embed + extract then delegate to the SQL builder."""
  emb = _StubEmbeddingService(dim=384)
  kw = _StubKeywordExtractor(keywords=["EKS", "Ingress"])

  sql, params = build_hybrid_rrf_engineer_query_from_ticket_text(
    title="Fix EKS Ingress",
    description="404 errors from ingress controller",
    embedding_service=emb,
    keyword_extractor=kw,
    semantic_limit=3,
    lexical_limit=4,
    result_limit=2,
    rrf_k=60,
  )

  assert "WITH semantic_results AS" in sql
  assert "lexical_results AS" in sql

  # params layout matches build_hybrid_rrf_engineer_query
  assert len(params) == 9
  assert params[1] == 3
  assert params[2] == "EKS Ingress"
  assert params[3] == 4
  assert params[8] == 2


def test_hybrid_rrf_from_ticket_text_empty_keywords_falls_back() -> None:
  """If extractor returns no keywords, wrapper should use fallback text."""
  emb = _StubEmbeddingService(dim=384)
  kw = _StubKeywordExtractor(keywords=[])

  sql, params = build_hybrid_rrf_engineer_query_from_ticket_text(
    title="Kubernetes networking",
    description="",
    embedding_service=emb,
    keyword_extractor=kw,
    keyword_fallback_text="Kubernetes networking",
    semantic_limit=3,
    lexical_limit=4,
    result_limit=2,
    rrf_k=60,
  )

  assert "ORDER BY rrf_score" in sql
  assert params[2] == "Kubernetes networking"
