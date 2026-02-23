"""Text embedding using sentence transformers."""

from ml_core.embeddings import get_embedding_service


def embed_text(texts: list[str]) -> list[list[float]]:
  """Embed texts using all-MiniLM-L6-v2 model.

  Args:
      texts: List of text strings to embed

  Returns:
      List of 384-dimensional embeddings
  """
  # Use the real embedding service from #8
  embedding_service = get_embedding_service(model_name="all-MiniLM-L6-v2")
  embeddings = embedding_service.embed_batch(texts)

  # Convert numpy arrays to lists for JSON serialization
  return [emb.tolist() for emb in embeddings]
