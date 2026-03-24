"""Retrieval and ranking utilities for Ticket-Forge.

This package contains database-query helpers for combining semantic search
(pgvector) with lexical search (Postgres full-text search) using RRF.
"""

from ml_core.retrieval.hybrid_retrieval import (  # noqa: F401
  build_hybrid_rrf_engineer_query,
  build_hybrid_rrf_engineer_query_from_ticket_text,
  vector_to_pgvector_text,
)

__all__ = [
  "build_hybrid_rrf_engineer_query",
  "build_hybrid_rrf_engineer_query_from_ticket_text",
  "vector_to_pgvector_text",
]
