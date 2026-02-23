"""Keyword extraction for technical skills from text."""

import re
from collections import Counter

from ml_core.keywords.skills_list import ALL_SKILLS, SKILL_ALIASES


class KeywordExtractor:
  """Extract technical skill keywords from text."""

  def __init__(self, custom_skills: set[str] | None = None) -> None:
    """Initialize the keyword extractor.

    Args:
        custom_skills: Additional custom skills to recognize
    """
    self.skills = ALL_SKILLS.copy()
    if custom_skills:
      self.skills.update(s.lower() for s in custom_skills)

    self.normalized_skills = {skill.lower(): skill for skill in self.skills}

    for alias, canonical in SKILL_ALIASES.items():
      self.normalized_skills[alias.lower()] = canonical

    # Compile single regex pattern for all skills (much faster!)
    pattern = (
      r"\b(" + "|".join(re.escape(s) for s in self.normalized_skills.keys()) + r")\b"
    )
    self.pattern = re.compile(pattern, re.IGNORECASE)

  def extract(self, text: str, top_n: int | None = None) -> list[str]:
    """Extract technical keywords from text.

    Args:
        text: Input text
        top_n: Return only top N most frequent keywords

    Returns:
        List of detected keywords in order of frequency
    """
    if not text or not text.strip():
      return []

    text_lower = text.lower()

    exact_matches = self._extract_exact_matches(text_lower)
    capitalized_terms = self._extract_capitalized_terms(text)

    all_keywords = exact_matches + capitalized_terms
    keyword_counts = Counter(all_keywords)

    return [kw for kw, _ in keyword_counts.most_common(top_n)]

  def _extract_exact_matches(self, text_lower: str) -> list[str]:
    """Extract skills using compiled regex."""
    matches = self.pattern.findall(text_lower)
    return [self.normalized_skills[m.lower()] for m in matches]

  def _extract_capitalized_terms(self, text: str) -> list[str]:
    """Extract capitalized terms that might be tech keywords."""
    pattern = r"\b[A-Z][A-Za-z0-9]*(?:[A-Z][a-z0-9]*)*\b"
    capitalized = re.findall(pattern, text)

    validated = []
    for term in capitalized:
      term_lower = term.lower()
      if term_lower in self.normalized_skills:
        validated.append(self.normalized_skills[term_lower])

    return validated

  def is_skill(self, keyword: str) -> bool:
    """Check if a keyword is a recognized skill."""
    return keyword.lower() in self.normalized_skills


_extractor: KeywordExtractor | None = None


def get_keyword_extractor(
  custom_skills: set[str] | None = None,
) -> KeywordExtractor:
  """Get or create the global keyword extractor instance."""
  global _extractor

  if _extractor is None:
    _extractor = KeywordExtractor(custom_skills=custom_skills)

  return _extractor
