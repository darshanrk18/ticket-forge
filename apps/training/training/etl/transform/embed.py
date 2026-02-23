"""Text embedding using sentence transformers."""

import torch
from ml_core.embeddings import get_embedding_service


def embed_text(texts: list[str]) -> list[list[float]]:
  """Embed texts using all-MiniLM-L6-v2 model on GPU.

  Args:
      texts: List of text strings to embed

  Returns:
      List of 384-dimensional embeddings
  """
  device = "cuda" if torch.cuda.is_available() else "cpu"

  embedding_service = get_embedding_service(model_name="all-MiniLM-L6-v2")

  batch_size = 512 if device == "cuda" else 128

  embeddings = embedding_service.embed_batch(
    texts, batch_size=batch_size, show_progress=True
  )

  return [emb.tolist() for emb in embeddings]
