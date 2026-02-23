"""Keyword extraction using technical skills list."""

from ml_core.keywords import get_keyword_extractor
from tqdm import tqdm


def extract_keywords(texts: list[str], top_k: int = 10) -> list[list[str]]:
  """Extract technical skill keywords from texts.

  Args:
      texts: List of text strings
      top_k: Maximum number of keywords to extract per text

  Returns:
      List of keyword lists
  """
  keyword_extractor = get_keyword_extractor()

  keywords = []
  for text in tqdm(texts, desc="Extracting keywords"):
    extracted = keyword_extractor.extract(text, top_n=top_k)
    keywords.append(extracted)

  return keywords
