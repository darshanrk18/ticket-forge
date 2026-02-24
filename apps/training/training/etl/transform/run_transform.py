import pandas as pd
import torch
from tqdm import tqdm
from training.etl.transform.embed import embed_text
from training.etl.transform.engineer_features import enrich_engineer_features
from training.etl.transform.keyword_extraction import extract_keywords
from training.etl.transform.normalize_text import normalize_ticket_text
from training.etl.transform.temporal_features import compute_business_completion_hours


def transform_records(records: list[dict]) -> list[dict]:
  """Run the complete ticket transformation pipeline in-memory."""
  device = "GPU" if torch.cuda.is_available() else "CPU"
  print("Using device:", device)

  df = pd.DataFrame(records)
  print("Loaded", len(df), "tickets")

  if df.empty:
    return []

  df["title"] = df.get("title", "")
  df["body"] = df.get("body", "")

  if "assignee" not in df.columns:
    df["assignee"] = pd.NA
  else:
    df["assignee"] = df["assignee"].fillna(pd.NA)

  if "seniority" not in df.columns:
    df["seniority"] = "mid"

  print("Normalizing text...")
  tqdm.pandas(desc="Normalizing")
  df["normalized_text"] = df.progress_apply(
    lambda r: normalize_ticket_text(r["title"], r["body"]),
    axis=1,
  )

  print("Computing temporal features...")
  tqdm.pandas(desc="Temporal features")
  df["completion_hours_business"] = df.progress_apply(
    lambda r: compute_business_completion_hours(
      r.get("created_at"),
      r.get("assigned_at"),
      r.get("closed_at"),
    ),
    axis=1,
  )

  print("Enriching engineer features...")
  df = enrich_engineer_features(df)

  print("Extracting keywords...")
  df["keywords"] = extract_keywords(df["normalized_text"].tolist())

  print("Generating embeddings...")
  df["embedding"] = embed_text(df["normalized_text"].tolist())
  df["embedding_model"] = "all-MiniLM-L6-v2"

  transformed = df.to_dict(orient="records")
  print("Transformed", len(transformed), "tickets")
  return transformed


def main() -> None:
  """Standalone runner hint."""
  print("Use training.etl.postload.load_tickets to run scrape -> transform -> db load.")


if __name__ == "__main__":
  main()
