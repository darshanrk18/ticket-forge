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

    # Build normalized skills map (lowercase -> canonical form)
    self.normalized_skills = {skill.lower(): skill for skill in self.skills}

    # Add aliases
    for alias, canonical in SKILL_ALIASES.items():
      self.normalized_skills[alias.lower()] = canonical

  def extract(self, text: str, top_n: int | None = None) -> list[str]:
    """Extract technical keywords from text.

    Args:
        text: Input text (ticket, resume, etc.)
        top_n: Return only top N most frequent keywords (None = all)

    Returns:
        List of detected keywords in order of frequency
    """
    if not text or not text.strip():
      return []

    # Normalize text
    text_lower = text.lower()

    # Extract exact matches
    exact_matches = self._extract_exact_matches(text_lower)

    # Extract capitalized terms (likely tech terms)
    capitalized_terms = self._extract_capitalized_terms(text)

    # Combine and count frequencies
    all_keywords = exact_matches + capitalized_terms
    keyword_counts = Counter(all_keywords)

    # Sort by frequency (most common first)
    return [kw for kw, _ in keyword_counts.most_common(top_n)]

  def _extract_exact_matches(self, text_lower: str) -> list[str]:
    """Extract skills that exactly match our skills list."""
    found_keywords = []

    # Word boundary regex for each skill
    for skill_lower, canonical in self.normalized_skills.items():
      # Use lookaround-based boundaries to match whole tokens, including
      # skills containing punctuation like C++ or C#.
      pattern = r"(?<!\w)" + re.escape(skill_lower) + r"(?!\w)"
      if re.search(pattern, text_lower):
        found_keywords.append(canonical)

    return found_keywords

  def _extract_capitalized_terms(self, text: str) -> list[str]:
    """Extract capitalized terms that might be tech keywords.

    Captures patterns like: AWS, S3, TypeScript, K8s
    """
    # Pattern for capitalized words/acronyms
    pattern = r"\b[A-Z][A-Za-z0-9]*(?:[A-Z][a-z0-9]*)*\b"
    capitalized = re.findall(pattern, text)

    # Filter and normalize
    validated = []
    for term in capitalized:
      term_lower = term.lower()
      # Check if it's in our skills or aliases
      if term_lower in self.normalized_skills:
        validated.append(self.normalized_skills[term_lower])

    return validated

  def is_skill(self, keyword: str) -> bool:
    """Check if a keyword is a recognized skill."""
    return keyword.lower() in self.normalized_skills


# Singleton instance
_extractor: KeywordExtractor | None = None


def get_keyword_extractor(
  custom_skills: set[str] | None = None,
) -> KeywordExtractor:
  """Get or create the global keyword extractor instance.

  Args:
      custom_skills: Additional skills to recognize

  Returns:
      KeywordExtractor instance
  """
  global _extractor

  if _extractor is None:
    _extractor = KeywordExtractor(custom_skills=custom_skills)

  return _extractor
