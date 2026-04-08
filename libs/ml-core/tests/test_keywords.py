"""Tests for keyword extraction."""

import pytest
from ml_core.keywords import KeywordExtractor, get_keyword_extractor


class TestKeywordExtractor:
  """Test cases for KeywordExtractor."""

  @pytest.fixture
  def extractor(self) -> KeywordExtractor:
    """Create a keyword extractor instance."""
    return KeywordExtractor()

  def test_extract_single_keyword(self, extractor: KeywordExtractor) -> None:
    """Test extracting a single keyword."""
    text = "Fix the Python bug in the API"
    keywords = extractor.extract(text)

    assert "python" in keywords

  def test_extract_multiple_keywords(self, extractor: KeywordExtractor) -> None:
    """Test extracting multiple keywords."""
    text = "Deploy Docker container to Kubernetes on AWS"
    keywords = extractor.extract(text)

    assert "docker" in keywords
    assert "kubernetes" in keywords
    assert "aws" in keywords

  def test_case_insensitive(self, extractor: KeywordExtractor) -> None:
    """Test that extraction is case-insensitive."""
    texts = [
      "Fix AWS issue",
      "Fix aws issue",
      "Fix Aws issue",
    ]

    for text in texts:
      keywords = extractor.extract(text)
      assert "aws" in keywords

  def test_kubernetes_alias(self, extractor: KeywordExtractor) -> None:
    """Test that K8s maps to Kubernetes."""
    text = "Fix K8s ingress timeout"
    keywords = extractor.extract(text)

    assert "kubernetes" in keywords

  def test_empty_text(self, extractor: KeywordExtractor) -> None:
    """Test with empty text."""
    assert extractor.extract("") == []
    assert extractor.extract("   ") == []

  def test_no_keywords(self, extractor: KeywordExtractor) -> None:
    """Test text with no technical keywords."""
    text = "Please review this document"
    keywords = extractor.extract(text)

    assert len(keywords) == 0

  def test_ticket_example(self, extractor: KeywordExtractor) -> None:
    """Test with realistic ticket text."""
    text = """
        Fix Kubernetes ingress timeout on AWS.
        The application is deployed using Docker containers and exposed via
        an ALB. The timeout occurs when making requests to the Python FastAPI
        backend connected to PostgreSQL database.
        """
    keywords = extractor.extract(text)

    expected = {
      "kubernetes",
      "aws",
      "docker",
      "python",
      "fastapi",
      "postgresql",
    }
    assert expected.issubset(set(keywords))

  def test_resume_example(self, extractor: KeywordExtractor) -> None:
    """Test with realistic resume text."""
    text = """
        Senior Backend Engineer with 5 years experience in Python, Go, and Java.
        Expert in building scalable microservices with Docker and Kubernetes.
        Strong experience with AWS (EC2, S3, Lambda), PostgreSQL, and Redis.
        Proficient in CI/CD with GitHub Actions and Terraform.
        """
    keywords = extractor.extract(text)

    expected = {
      "python",
      "go",
      "java",
      "docker",
      "kubernetes",
      "aws",
      "ec2",
      "s3",
      "lambda",
      "postgresql",
      "redis",
      "github",
      "terraform",
    }
    assert expected.issubset(set(keywords))

  def test_frequency_ordering(self, extractor: KeywordExtractor) -> None:
    """Test that keywords are ordered by frequency."""
    text = "Python Python Python Java Java SQL"
    keywords = extractor.extract(text)

    # Python should appear first (most frequent)
    assert keywords[0] == "python"
    assert keywords[1] == "java"
    assert keywords[2] == "sql"

  def test_top_n_limit(self, extractor: KeywordExtractor) -> None:
    """Test limiting results to top N keywords."""
    text = "Python Java JavaScript Go Rust C++ Ruby"
    keywords = extractor.extract(text, top_n=3)

    assert len(keywords) == 3

  def test_is_skill(self, extractor: KeywordExtractor) -> None:
    """Test checking if a keyword is a recognized skill."""
    assert extractor.is_skill("python")
    assert extractor.is_skill("Python")
    assert extractor.is_skill("PYTHON")
    assert not extractor.is_skill("notaskill")

  def test_custom_skills(self) -> None:
    """Test adding custom skills."""
    custom = {"myframework", "customtool"}
    extractor = KeywordExtractor(custom_skills=custom)

    text = "Using MyFramework and CustomTool"
    keywords = extractor.extract(text)

    assert "myframework" in keywords
    assert "customtool" in keywords

  def test_extract_handles_large_capitalized_noise(
    self,
    extractor: KeywordExtractor,
  ) -> None:
    """Large capitalized noise should not prevent finding real skills."""
    text = f"{'A' * 4000} Python AWS"
    keywords = extractor.extract(text)

    assert "python" in keywords
    assert "aws" in keywords

  def test_get_keyword_extractor_singleton(self) -> None:
    """Test that get_keyword_extractor returns same instance."""
    extractor1 = get_keyword_extractor()
    extractor2 = get_keyword_extractor()

    assert extractor1 is extractor2
