"""Transform pipeline for sampled tickets."""

import json
from pathlib import Path

from training.etl.transform.run_transform import transform_records

INPUT_PATH = Path("data/github_issues/sample_tickets.json")
OUTPUT_PATH = Path("data/github_issues/sample_tickets_transformed.jsonl")


def load_records(path: Path) -> list[dict]:
  """Load records from JSON file."""
  with open(path, encoding="utf-8") as f:
    data = json.load(f)

  if isinstance(data, list):
    return data

  if isinstance(data, dict) and "tickets" in data:
    return data["tickets"]

  return [data]


def main() -> None:
  """Run the transformation pipeline on sampled tickets."""
  records = load_records(INPUT_PATH)
  print("Loaded", len(records), "tickets")

  transformed = transform_records(records)

  OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
  print("Saving to", OUTPUT_PATH)
  with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    for row in transformed:
      f.write(json.dumps(row) + "\n")

  print("Saved", len(transformed), "records")


if __name__ == "__main__":
  main()
