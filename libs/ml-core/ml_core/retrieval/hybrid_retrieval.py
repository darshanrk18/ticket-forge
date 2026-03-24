"""Hybrid recommendation retrieval (pgvector + TSVECTOR) with RRF.

Implements query-building helpers for a hybrid retrieval engine:
1. Semantic retrieval via pgvector cosine distance on `users.profile_vector`.
2. Lexical retrieval via Postgres full-text search on `users.skill_keywords`.
3. Merging the two ranked lists using Reciprocal Rank Fusion (RRF).

The module is intentionally query-builder only: callers decide how to
execute the SQL (e.g., psycopg2 cursor) to keep ml-core independent from
database driver concerns.
"""

from __future__ import annotations

from typing import Protocol, Sequence

import numpy as np


class _EmbeddingService(Protocol):
  """Minimal protocol for embedding service dependency injection."""

  def embed_text(self, text: str) -> np.ndarray | Sequence[float]: ...


class _KeywordExtractor(Protocol):
  """Minimal protocol for keyword extractor dependency injection."""

  def extract(self, text: str, top_n: int | None = None) -> list[str]: ...


def vector_to_pgvector_text(vector: Sequence[float], *, dim: int = 384) -> str:
  """Convert a numeric embedding into a pgvector literal string.

  Args:
    vector: Embedding vector values.
    dim: Expected embedding dimensionality.

  Returns:
    A string like ``"[0.1,-0.2,0.3,...]"`` that can be cast to
    ``::vector(dim)`` in Postgres.

  Raises:
    ValueError: If the input vector dimensionality does not match `dim`.
  """
  values = list(vector)
  if len(values) != dim:
    msg = f"Expected embedding length {dim}, got {len(values)}"
    raise ValueError(msg)

  # Ensure stable formatting and avoid numpy scalar repr differences.
  return "[" + ",".join(str(float(x)) for x in values) + "]"


def build_hybrid_rrf_engineer_query(  # noqa: PLR0913
  *,
  ticket_vector: Sequence[float],
  keyword_query_text: str,
  semantic_limit: int = 10,
  lexical_limit: int = 10,
  result_limit: int = 5,
  rrf_k: int = 60,
  missing_rank: int | None = None,
  vector_dim: int = 384,
) -> tuple[str, tuple[object, ...]]:
  """Build a hybrid engineer retrieval query using RRF.

  The query returns the top `result_limit` engineers ranked by:

  ``rrf_score = 1/(rrf_k + rank_semantic) + 1/(rrf_k + rank_lexical)``

  where missing ranks (an engineer not appearing in one ranked list) are
  replaced with `missing_rank` (a large value).

  Args:
    ticket_vector: Ticket embedding vector (length must match `vector_dim`).
    keyword_query_text: Plain-text keywords for tsquery generation.
      Example: ``"EKS Ingress"``.
    semantic_limit: How many rows to keep in the semantic (vector) list.
    lexical_limit: How many rows to keep in the lexical (tsvector) list.
    result_limit: Final number of engineers returned.
    rrf_k: RRF constant (typical values: 60).
    missing_rank: Rank used when a candidate is absent from a ranked list.
      If omitted, defaults to ``max(semantic_limit, lexical_limit) + 1``.
    vector_dim: Embedding dimensionality. Currently must be 384 to match the
      schema in `scripts/postgres/init/02_schema.sql`.

  Returns:
    A ``(sql, params)`` tuple ready for ``cursor.execute(sql, params)``.

  Raises:
    ValueError: If parameters are invalid or the schema dimension is not
      supported.
  """
  if vector_dim != 384:
    msg = "Only vector_dim=384 is supported by this query builder."
    raise ValueError(msg)

  if not keyword_query_text.strip():
    msg = "keyword_query_text must be non-empty."
    raise ValueError(msg)

  if semantic_limit <= 0 or lexical_limit <= 0 or result_limit <= 0:
    msg = "semantic_limit, lexical_limit, and result_limit must be > 0."
    raise ValueError(msg)

  if rrf_k <= 0:
    msg = "rrf_k must be > 0."
    raise ValueError(msg)

  if missing_rank is None:
    missing_rank = max(semantic_limit, lexical_limit) + 1

  ticket_vector_text = vector_to_pgvector_text(ticket_vector, dim=vector_dim)

  # NOTE: `to_tsquery('english', ...)` parses plain text into a tsquery
  # (similar to AND-ing tokens). Using `plainto_tsquery` would also work;
  # `to_tsquery` is kept to mirror the example queries already in the repo.
  sql = """
    WITH semantic_results AS (
      SELECT
        u.member_id,
        u.full_name,
        ROW_NUMBER() OVER (ORDER BY u.profile_vector <=> q.query_vector) AS rank,
        1 - (u.profile_vector <=> q.query_vector) AS similarity
      FROM users u
      CROSS JOIN (SELECT %s::vector(384) AS query_vector) q
      ORDER BY u.profile_vector <=> q.query_vector
      LIMIT %s
    ),
    lexical_results AS (
      SELECT
        u.member_id,
        u.full_name,
        ROW_NUMBER() OVER (ORDER BY ts_rank(u.skill_keywords, query) DESC) AS rank,
        ts_rank(u.skill_keywords, query) AS bm25_score
      FROM users u
      CROSS JOIN to_tsquery('english', %s) AS query
      WHERE u.skill_keywords @@ query
      ORDER BY ts_rank(u.skill_keywords, query) DESC
      LIMIT %s
    ),
    rrf_scores AS (
      SELECT
        COALESCE(s.member_id, l.member_id) AS member_id,
        COALESCE(s.full_name, l.full_name) AS full_name,
        (1.0 / (%s + COALESCE(s.rank, %s)))
          + (1.0 / (%s + COALESCE(l.rank, %s))) AS rrf_score,
        s.rank AS semantic_rank,
        l.rank AS lexical_rank,
        s.similarity AS semantic_similarity,
        l.bm25_score AS lexical_score
      FROM semantic_results s
      FULL OUTER JOIN lexical_results l ON s.member_id = l.member_id
    )
    SELECT
      member_id,
      full_name,
      rrf_score,
      semantic_rank,
      lexical_rank,
      semantic_similarity,
      lexical_score
    FROM rrf_scores
    ORDER BY rrf_score DESC, member_id ASC
    LIMIT %s
  """.strip()

  params: tuple[object, ...] = (
    ticket_vector_text,
    semantic_limit,
    keyword_query_text,
    lexical_limit,
    rrf_k,
    missing_rank,
    rrf_k,
    missing_rank,
    result_limit,
  )
  return sql, params


def build_hybrid_rrf_engineer_query_from_ticket_text(  # noqa: PLR0913
  *,
  title: str,
  description: str,
  semantic_limit: int = 10,
  lexical_limit: int = 10,
  result_limit: int = 5,
  rrf_k: int = 60,
  vector_dim: int = 384,
  embedding_service: _EmbeddingService | None = None,
  keyword_extractor: _KeywordExtractor | None = None,
  keyword_top_n: int = 10,
  keyword_fallback_text: str | None = None,
) -> tuple[str, tuple[object, ...]]:  # noqa: PLR0913
  """Build the hybrid engineer query from raw ticket text.

  This function is the ML-side glue for issue #9:
  - embed the ticket using `ml_core.embeddings`
  - extract technical skills using `ml_core.keywords`
  - delegate SQL/RRF construction to :func:`build_hybrid_rrf_engineer_query`

  Args:
    title: Ticket title.
    description: Ticket body/description.
    semantic_limit: How many engineers to keep in semantic (vector) list.
    lexical_limit: How many engineers to keep in lexical (full-text) list.
    result_limit: Final number of engineers returned.
    rrf_k: Reciprocal Rank Fusion constant (typical value: 60).
    vector_dim: Embedding dimensionality (must match schema: 384).
    embedding_service: Optional embedding service with `embed_text(text)`.
      If not provided, uses `ml_core.embeddings.get_embedding_service()`.
    keyword_extractor: Optional extractor with `extract(text, top_n)`.
      If not provided, uses `ml_core.keywords.get_keyword_extractor()`.
    keyword_top_n: Top N skills to use for the lexical query.
    keyword_fallback_text: Text to use if no keywords are extracted.
      Defaults to ``title``.

  Returns:
    A ``(sql, params)`` tuple ready for DB execution.
  """
  # Local imports to keep module import time light.
  from ml_core.embeddings import get_embedding_service
  from ml_core.keywords import get_keyword_extractor

  if not title and not description:
    msg = "title/description must not both be empty"
    raise ValueError(msg)

  effective_embedding_service = embedding_service or get_embedding_service()
  effective_keyword_extractor = keyword_extractor or get_keyword_extractor()

  combined_text = (title or "").strip() + "\n" + (description or "").strip()
  if not combined_text.strip():
    msg = "Combined ticket text must not be empty"
    raise ValueError(msg)

  raw_vector = effective_embedding_service.embed_text(combined_text)
  # `SentenceTransformer.encode()` returns a numpy array, while tests may
  # inject a list. Normalize both to a plain list[float].
  if isinstance(raw_vector, np.ndarray):
    vector_list = raw_vector.tolist()
  else:
    vector_list = list(raw_vector)
  ticket_vector = [float(x) for x in vector_list]

  # ml-core keyword extractor returns a list[str] ordered by frequency.
  keywords = effective_keyword_extractor.extract(combined_text, top_n=keyword_top_n)
  keyword_query_text = " ".join(keywords).strip()
  if not keyword_query_text:
    fallback = keyword_fallback_text or title
    keyword_query_text = (fallback or "").strip()

  return build_hybrid_rrf_engineer_query(
    ticket_vector=ticket_vector,
    keyword_query_text=keyword_query_text,
    semantic_limit=semantic_limit,
    lexical_limit=lexical_limit,
    result_limit=result_limit,
    rrf_k=rrf_k,
    vector_dim=vector_dim,
  )
