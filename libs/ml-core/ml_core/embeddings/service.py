"""Embedding service for converting text to semantic vectors."""

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Error messages
EMPTY_TEXT_ERROR = "Text cannot be empty"
EMPTY_LIST_ERROR = "Texts list cannot be empty"
DEFAULT_MODEL_BUNDLE_PATH = "/opt/models/all-MiniLM-L6-v2"


def _resolve_model_source(model_name: str) -> tuple[str, bool]:
  """Prefer a bundled local model copy when available."""
  configured_path = os.environ.get("MLCORE_EMBEDDING_MODEL_PATH", "").strip()
  candidate = Path(configured_path or DEFAULT_MODEL_BUNDLE_PATH)
  if candidate.exists():
    return str(candidate), True
  return model_name, False


class EmbeddingService:
  """Service to convert text data into high-dimensional vectors.

  Uses pre-trained models to ensure tickets and engineer profiles are
  embedded in the same vector space for semantic similarity comparisons.
  """

  embedding_dim: int

  def __init__(
    self,
    model_name: str = "all-MiniLM-L6-v2",
    device: Optional[str] = None,
  ) -> None:
    """Initialize the embedding service.

    Args:
        model_name: Name of the sentence-transformer model to use
        device: Device to run model on ('cuda', 'cpu', or None)
    """
    model_source, local_files_only = _resolve_model_source(model_name)
    logger.info(
      "Loading embedding model source=%s local_files_only=%s",
      model_source,
      local_files_only,
    )
    self.model_name = model_name
    self.model = SentenceTransformer(
      model_source,
      device=device,
      local_files_only=local_files_only,
    )
    dim = self.model.get_sentence_embedding_dimension()
    if dim is None:
      msg = "Model returned None for embedding dimension"
      raise RuntimeError(msg)
    self.embedding_dim = dim
    logger.info(f"Model loaded. Embedding dimension: {self.embedding_dim}")

  def embed_text(self, text: str) -> np.ndarray:
    """Convert a single text string into a semantic vector.

    Args:
        text: Cleaned text string from ticket or engineer profile

    Returns:
        384-dimensional dense vector representing semantic meaning

    Raises:
        ValueError: If text is empty or None
    """
    if not text or not text.strip():
      raise ValueError(EMPTY_TEXT_ERROR)

    return self.model.encode(
      text,
      convert_to_numpy=True,
      show_progress_bar=False,
    )

  def embed_batch(
    self,
    texts: list[str],
    batch_size: int = 32,
    show_progress: bool = False,
  ) -> np.ndarray:
    """Embed multiple texts efficiently in batches.

    Args:
        texts: List of text strings to embed
        batch_size: Number of texts to process at once
        show_progress: Whether to show a progress bar

    Returns:
        Array of embeddings with shape (n_texts, 384)

    Raises:
        ValueError: If texts list is empty
    """
    if not texts:
      raise ValueError(EMPTY_LIST_ERROR)

    return self.model.encode(
      texts,
      batch_size=batch_size,
      convert_to_numpy=True,
      show_progress_bar=show_progress,
    )

  def get_embedding_dimension(self) -> int:
    """Get the dimension of embeddings produced by this service."""
    if self.embedding_dim is None:
      msg = "Embedding dimension not initialized"
      raise RuntimeError(msg)
    return self.embedding_dim


# Singleton instance for reuse across the application
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service(
  model_name: str = "all-MiniLM-L6-v2",
  force_reload: bool = False,
) -> EmbeddingService:
  """Get or create the global embedding service instance.

  Args:
      model_name: Model to use (only applies on first call)
      force_reload: Force reloading the model

  Returns:
      EmbeddingService instance
  """
  global _embedding_service

  if _embedding_service is None or force_reload:
    _embedding_service = EmbeddingService(model_name=model_name)

  return _embedding_service
