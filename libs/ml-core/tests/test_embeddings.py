"""Tests for embedding service."""

import numpy as np
import pytest
from ml_core.embeddings import EmbeddingService, get_embedding_service
from ml_core.embeddings.service import _resolve_model_source


class TestEmbeddingService:
  """Test cases for EmbeddingService."""

  @pytest.fixture
  def embedding_service(self) -> EmbeddingService:
    """Create an embedding service instance."""
    return EmbeddingService()

  def test_initialization(self, embedding_service: EmbeddingService) -> None:
    """Test that service initializes correctly."""
    assert embedding_service.embedding_dim == 384
    assert embedding_service.model_name == "all-MiniLM-L6-v2"

  def test_embed_text_returns_correct_shape(
    self, embedding_service: EmbeddingService
  ) -> None:
    """Test that embedding has correct dimensions."""
    text = "Database connection timeout error in production"
    embedding = embedding_service.embed_text(text)

    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (384,)

  def test_embed_text_with_empty_string_raises_error(
    self, embedding_service: EmbeddingService
  ) -> None:
    """Test that empty text raises ValueError."""
    with pytest.raises(ValueError, match="Text cannot be empty"):
      embedding_service.embed_text("")

  def test_embed_text_deterministic(self, embedding_service: EmbeddingService) -> None:
    """Test that same text produces same embedding."""
    text = "Senior backend engineer with database expertise"

    embedding1 = embedding_service.embed_text(text)
    embedding2 = embedding_service.embed_text(text)

    np.testing.assert_array_almost_equal(embedding1, embedding2)

  def test_embed_batch_returns_correct_shape(
    self, embedding_service: EmbeddingService
  ) -> None:
    """Test batch embedding returns correct shape."""
    texts = [
      "Database error in production",
      "Frontend bug in login page",
      "API performance issue",
    ]

    embeddings = embedding_service.embed_batch(texts)

    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape == (3, 384)

  def test_embed_batch_with_empty_list_raises_error(
    self, embedding_service: EmbeddingService
  ) -> None:
    """Test that empty list raises ValueError."""
    with pytest.raises(ValueError, match="Texts list cannot be empty"):
      embedding_service.embed_batch([])

  def test_semantic_similarity(self, embedding_service: EmbeddingService) -> None:
    """Test that semantically similar texts have similar embeddings."""
    ticket = "Database connection timeout error"
    similar_profile = "Backend engineer with database and SQL expertise"
    dissimilar_profile = "Frontend developer with React and CSS skills"

    ticket_emb = embedding_service.embed_text(ticket)
    similar_emb = embedding_service.embed_text(similar_profile)
    dissimilar_emb = embedding_service.embed_text(dissimilar_profile)

    # Cosine similarity
    def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
      return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    sim_similar = cosine_sim(ticket_emb, similar_emb)
    sim_dissimilar = cosine_sim(ticket_emb, dissimilar_emb)

    # Similar profiles should have higher similarity
    assert sim_similar > sim_dissimilar

  def test_get_embedding_service_singleton(self) -> None:
    """Test that get_embedding_service returns same instance."""
    service1 = get_embedding_service()
    service2 = get_embedding_service()

    assert service1 is service2

  def test_prefers_bundled_model_path(
    self, monkeypatch: pytest.MonkeyPatch, tmp_path
  ) -> None:
    """Bundled model path should be used offline when configured."""
    bundled_model = tmp_path / "all-MiniLM-L6-v2"
    bundled_model.mkdir()

    captured: dict[str, object] = {}

    class FakeSentenceTransformer:
      def __init__(
        self,
        model_name: str,
        *,
        device: str | None = None,
        local_files_only: bool = False,
      ) -> None:
        captured["model_name"] = model_name
        captured["device"] = device
        captured["local_files_only"] = local_files_only

      def get_sentence_embedding_dimension(self) -> int:
        return 384

    monkeypatch.setenv("MLCORE_EMBEDDING_MODEL_PATH", str(bundled_model))
    monkeypatch.setattr(
      "ml_core.embeddings.service.SentenceTransformer",
      FakeSentenceTransformer,
    )

    model_source, local_only = _resolve_model_source("all-MiniLM-L6-v2")
    assert model_source == str(bundled_model)
    assert local_only is True

    service = EmbeddingService()
    assert service.embedding_dim == 384
    assert captured["model_name"] == str(bundled_model)
    assert captured["local_files_only"] is True
