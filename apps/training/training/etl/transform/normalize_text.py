"""Text normalization for tickets."""

import re
from typing import Match

CODE_BLOCK_RE = re.compile(r"```(.*?)```", re.DOTALL)
IMAGE_LINK_RE = re.compile(r"!\[.*?\]\(.*?\)")
LINK_RE = re.compile(r"\[.*?\]\(.*?\)")
INLINE_CODE_RE = re.compile(r"`([^`]*)`")


def _truncate_code_block(code: str) -> str:
  """Truncate code block intelligently based on size."""
  lines = code.strip().splitlines()

  if len(lines) <= 15:
    return "\n".join(lines)
  if len(lines) <= 50:
    return "\n".join(lines[:5] + ["..."] + lines[-5:])
  return "\n".join(lines[:10] + ["..."] + lines[-10:])


def normalize_ticket_text(title: str, body: str) -> str:
  """Normalize ticket text by removing markdown and truncating code blocks.

  Args:
      title: Ticket title
      body: Ticket body

  Returns:
      Normalized text string
  """
  body = body or ""

  # Handle fenced code blocks
  def _code_repl(match: Match[str]) -> str:
    return _truncate_code_block(match.group(1))

  body = CODE_BLOCK_RE.sub(_code_repl, body)

  # Remove images and links
  body = IMAGE_LINK_RE.sub("", body)
  body = LINK_RE.sub("", body)

  # Inline code: keep content, remove backticks
  body = INLINE_CODE_RE.sub(r"\1", body)

  # Remove markdown symbols
  body = re.sub(r"[>#*_~-]", " ", body)

  # Normalize whitespace
  body = re.sub(r"\n{3,}", "\n\n", body)
  body = re.sub(r"\s+", " ", body).strip()

  text = f"{title.strip()}\n\n{body}".strip()
  return text[:4000]  # hard cap
