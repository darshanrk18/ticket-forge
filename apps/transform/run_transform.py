import json
from pathlib import Path

import pandas as pd
from embed import embed_text
from engineer_features import enrich_engineer_features
from keyword_extraction import extract_keywords
from normalize_text import normalize_ticket_text
from temporal_features import compute_business_completion_hours

# -----------------------------
# Paths
# -----------------------------
INPUT_PATH = Path("data/github_issues/all_tickets.json")
OUTPUT_PATH = Path("data/github_issues/tickets_transformed_improved.jsonl")


# -----------------------------
# Data loader (robust)
# -----------------------------
def load_records(path: Path) -> list[dict]:
  """Load records from JSON file.

  Args:
      path: Path to JSON file

  Returns:
      List of ticket dictionaries
  """
  with open(path, encoding="utf-8") as f:
    data = json.load(f)

  # If it's already a list, return it
  if isinstance(data, list):
    return data

  # If it's an object with "tickets" key
  if isinstance(data, dict) and "tickets" in data:
    return data["tickets"]

  # Otherwise return as single-item list
  return [data]


# -----------------------------
# Main pipeline
# -----------------------------
def main() -> None:
  """Run the complete ticket transformation pipeline."""
  records = load_records(INPUT_PATH)
  df = pd.DataFrame(records)

  print(f"Loaded {len(df)} tickets")

  # Ensure required fields exist
  df["title"] = df.get("title", "")
  df["body"] = df.get("body", "")
  df["createdAt"] = df.get("createdAt")
  df["closedAt"] = df.get("closedAt")

  if "assignee" not in df.columns:
    df["assignee"] = "unknown"

  if "seniority" not in df.columns:
    df["seniority"] = "mid"

  # -----------------------------
  # Text normalization
  # -----------------------------
  print("Normalizing text...")
  df["normalized_text"] = df.apply(
    lambda r: normalize_ticket_text(r["title"], r["body"]),
    axis=1,
  )

  # -----------------------------
  # Temporal features
  # -----------------------------
  print("Computing temporal features...")
  df["completion_hours_business"] = df.apply(
    lambda r: compute_business_completion_hours(
      r.get("created_at"),
      r.get("assigned_at"),
      r.get("closed_at"),
    ),
    axis=1,
  )

  # -----------------------------
  # Engineer features
  # -----------------------------
  print("Enriching engineer features...")
  df = enrich_engineer_features(df)

  # -----------------------------
  # Keyword extraction
  # -----------------------------
  print("Extracting keywords...")
  df["keywords"] = extract_keywords(df["normalized_text"].tolist())

  # -----------------------------
  # Embeddings (stub)
  # -----------------------------
  print("Generating embeddings...")
  df["embedding"] = embed_text(df["normalized_text"].tolist())
  df["embedding_model"] = "all-MiniLM-L6-v2"

  # -----------------------------
  # Write output (JSONL)
  # -----------------------------
  OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

  with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    for row in df.to_dict(orient="records"):
      f.write(json.dumps(row) + "\n")

  print(f"✓ Saved {len(df)} records to {OUTPUT_PATH}")


if __name__ == "__main__":
  main()
