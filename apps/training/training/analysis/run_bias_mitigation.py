"""Apply bias mitigation to ticket training data.

Produces two outputs:
  - tickets_balanced.jsonl  : resampled dataset for use as training input
  - sample_weights.json     : per-sample inverse-frequency weights (alternative
                              to resampling — use one or the other, not both)
"""

import argparse
import json
from pathlib import Path

import pandas as pd
from shared.configuration import Paths
from training.bias import BiasMitigator

GROUP_COL = "repo"


def load_tickets(path: str | Path) -> pd.DataFrame:
  """Load tickets from a JSONL file."""
  tickets = []
  with open(path, encoding="utf-8") as f:
    for line in f:
      if line.strip():
        tickets.append(json.loads(line))
  return pd.DataFrame(tickets)


def print_distribution(df: pd.DataFrame, label: str) -> None:
  """Print group distribution counts."""
  print(f"\n{label}:")
  for group, count in df[GROUP_COL].value_counts().items():
    print(f"  {group}: {count:,}")


def run_bias_mitigation_weights(
  data_path: str | Path, output_dir: str | Path | None = None
) -> dict:
  """Run bias mitigation (sample weights mode) and return results.

  Args:
      data_path: Path to tickets JSONL file
      output_dir: Directory to save weights. If None, uses data directory.

  Returns:
      Dictionary with weights_path and distribution analysis
  """
  data_path = Path(data_path)
  if output_dir is None:
    output_dir = data_path.parent
  else:
    output_dir = Path(output_dir)

  print(f"Loading data from {data_path}...")
  df = load_tickets(str(data_path))
  print(f"Loaded {len(df):,} tickets")

  print_distribution(df, "ORIGINAL DISTRIBUTION BY REPO")

  # --- Strategy: Sample weights ---
  # Computed on the ORIGINAL data. Pass these to the trainer via sample_weight=.
  # Do NOT use in combination with the resampled dataset.
  print("\nComputing sample weights (do not combine with resampled data)...")
  weights = BiasMitigator.compute_sample_weights(df, GROUP_COL)

  print("\nSAMPLE WEIGHTS BY REPO:")
  weights_by_group: dict[str, float] = {}
  for group in df[GROUP_COL].unique():
    mask = df[GROUP_COL] == group
    weight = float(weights.loc[mask].iloc[0])
    weights_by_group[str(group)] = round(weight, 4)
    print(f"  {group}: {weight:.4f}")

  weights_path = output_dir / "sample_weights.json"
  with open(weights_path, "w", encoding="utf-8") as f:
    json.dump(
      {
        "group_col": GROUP_COL,
        "weights_by_group": weights_by_group,
        "note": (
          "Apply via fit(sample_weight=...). Do not combine with resampled data."
        ),
      },
      f,
      indent=2,
    )

  print(f"Saved sample weights → {weights_path}")

  return {
    "weights_path": str(weights_path),
    "weights_by_group": weights_by_group,
    "total_tickets": len(df),
    "distribution": df[GROUP_COL].value_counts().to_dict(),
  }


def main(mode: str = "weight") -> None:
  """Run bias mitigation on ticket data (CLI entry point)."""
  data_dir = Paths.data_root / "github_issues"
  data_path = data_dir / "tickets_transformed_improved.jsonl"

  if mode == "resample":
    # --- Strategy: Resampling ---
    df = load_tickets(str(data_path))
    print(f"Loaded {len(df):,} tickets")
    print_distribution(df, "ORIGINAL DISTRIBUTION BY REPO")

    print("\nApplying resampling...")
    balanced_df = BiasMitigator.resample_underrepresented(df, GROUP_COL)

    print_distribution(balanced_df, "BALANCED DISTRIBUTION BY REPO")

    balanced_path = data_dir / "tickets_balanced.jsonl"
    with open(balanced_path, "w", encoding="utf-8") as f:
      for row in balanced_df.to_dict(orient="records"):
        f.write(json.dumps(row) + "\n")
    print(f"\nSaved {len(balanced_df):,} tickets → {balanced_path}")
    print("\nDone. Training input: tickets_balanced.jsonl")

  elif mode == "weight":
    run_bias_mitigation_weights(data_path, output_dir=data_dir)
    print(
      "\nDone. Training input: tickets_transformed_improved.jsonl + sample_weights.json"
    )


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="Apply bias mitigation to ticket data.")
  parser.add_argument(
    "--mode",
    choices=["weight", "resample"],
    default="weight",
    help="Mitigation strategy: 'weight' (default) computes per-sample weights; "
    "'resample' upsamples minority groups to a balanced dataset.",
  )
  _args = parser.parse_args()
  main(_args.mode)
