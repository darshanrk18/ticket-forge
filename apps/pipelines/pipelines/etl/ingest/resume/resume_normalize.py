"""Step 2: Resume Normalizer - Cleans resume text by removing PII and unwanted data."""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class NormalizedResume:
  """Represents a resume with normalized (cleaned) content."""

  engineer_id: str
  filename: str
  normalized_content: str
  removed_items: Dict[str, List[str]]


class ResumeNormalizer:
  """Normalizes resume text by removing PII and other unwanted data."""

  PATTERNS = {
    "phone": [
      r"[\+]?[(]?[0-9]{1,3}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,4}[-\s\.]?[0-9]{1,9}",
      r"\(\d{3}\)\s*\d{3}[-.\s]?\d{4}",
      r"\d{3}[-.\s]?\d{3}[-.\s]?\d{4}",
    ],
    "email": [
      r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    ],
    "url": [
      r"https?://[^\s]+",
      r"www\.[^\s]+",
      r"(?:linkedin|github|twitter|gitlab|bitbucket)\.com/[^\s]*",
    ],
    "address": [
      r"\d{1,5}\s+[\w\s]{1,30}(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr|court|ct|way|place|pl)\.?",
      r"[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?,\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?",
      r"[A-Z][a-zA-Z]+,\s*[A-Z]{2}(?=\s|$|•|\||\n)",
    ],
    "dates": [
      r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*\d{0,2},?\s*\d{2,4}",
      r"\d{1,2}/\d{1,2}/\d{2,4}",
      r"\d{4}\s*[-–—]\s*(?:\d{4}|[Pp]resent|[Cc]urrent|[Nn]ow)",
      r"(?:19|20)\d{2}",
    ],
    "gpa": [
      r"GPA[:\s]*\d+\.?\d*(?:\s*/\s*\d+\.?\d*)?",
      r"\d+\.\d+\s*/\s*4\.0",
    ],
  }

  def __init__(  # noqa: PLR0913
    self,
    *,
    remove_phone: bool = True,
    remove_email: bool = True,
    remove_url: bool = True,
    remove_address: bool = True,
    remove_dates: bool = True,
    remove_gpa: bool = True,
  ) -> None:
    """Initialize the normalizer.

    Args:
      remove_phone: Whether to remove phone numbers.
      remove_email: Whether to remove email addresses.
      remove_url: Whether to remove URLs.
      remove_address: Whether to remove physical addresses.
      remove_dates: Whether to remove dates.
      remove_gpa: Whether to remove GPA information.
    """
    self.config = {
      "phone": remove_phone,
      "email": remove_email,
      "url": remove_url,
      "address": remove_address,
      "dates": remove_dates,
      "gpa": remove_gpa,
    }

  def normalize(self, text: str) -> Tuple[str, Dict[str, List[str]]]:
    """Normalize resume text by removing configured PII patterns.

    Args:
      text: Raw resume text.

    Returns:
      Tuple of (normalized_text, removed_items_dict).
    """
    removed = {}
    normalized = text

    for category, should_remove in self.config.items():
      if not should_remove:
        continue

      patterns = self.PATTERNS.get(category, [])
      category_matches = []

      for pattern in patterns:
        matches = re.findall(pattern, normalized, re.IGNORECASE)
        category_matches.extend(matches)
        normalized = re.sub(pattern, " ", normalized, flags=re.IGNORECASE)

      if category_matches:
        removed[category] = list(set(category_matches))

    normalized = self._clean_formatting(normalized)
    return normalized, removed

  def _clean_formatting(self, text: str) -> str:
    """Clean up formatting artifacts and extra whitespace."""
    text = re.sub(r"[•▪▸►◆◇○●■□–—|·]", " ", text)
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line)
    return text.strip()

  def normalize_batch(
    self,
    extracted_resumes: List[Any],
  ) -> List[NormalizedResume]:
    """Normalize a batch of extracted resumes.

    Args:
      extracted_resumes: List of extracted resume objects.

    Returns:
      List of normalized resume objects.
    """
    results = []

    for resume in extracted_resumes:
      normalized_text, removed = self.normalize(resume.raw_content)
      results.append(
        NormalizedResume(
          engineer_id=resume.engineer_id,
          filename=resume.filename,
          normalized_content=normalized_text,
          removed_items=removed,
        )
      )

    return results
