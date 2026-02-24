"""Run bias detection analysis on ticket prediction data."""

import json
from pathlib import Path

import pandas as pd
from shared.configuration import Paths
from training.bias import DataSlicer


def run_bias_detection(data_path: str | Path) -> dict:
  """Analyze bias in ticket assignment predictions and return formatted report.

  Args:
      data_path: Path to tickets JSONL file

  Returns:
      Dictionary with analysis results suitable for email reporting
  """
  print("Starting bias detection analysis...\n")

  # Load transformed tickets
  data_path = Path(data_path)
  print(f"Loading data from {data_path}...")
  tickets = []
  with open(data_path, encoding="utf-8") as f:
    for line in f:
      if line.strip():
        tickets.append(json.loads(line))

  df = pd.DataFrame(tickets)
  print(f"Loaded {len(df)} tickets\n")

  print("DATA DISTRIBUTION ANALYSIS")

  # Initialize slicer
  slicer = DataSlicer(df)

  # Collect all analysis results
  analysis = {
    "total_tickets": len(df),
    "by_repository": {},
    "by_seniority": {},
    "by_completion_time": {},
    "by_label": {},
  }

  # By repository
  print("\nBY REPOSITORY:")
  for repo, slice_df in slicer.slice_by_repo().items():
    avg = slice_df["completion_hours_business"].mean()
    analysis["by_repository"][repo] = {
      "count": len(slice_df),
      "avg_hours": round(avg, 2),
    }
    print(f"  {repo}: {len(slice_df)} tickets, avg hours: {round(avg, 2)}")

  # By seniority
  print("\nBY SENIORITY:")
  for seniority, slice_df in slicer.slice_by_seniority().items():
    avg = slice_df["completion_hours_business"].mean()
    analysis["by_seniority"][seniority] = {
      "count": len(slice_df),
      "avg_hours": round(avg, 2),
    }
    print(f"  {seniority}: {len(slice_df)} tickets, avg hours: {round(avg, 2)}")

  # By completion time
  print("\nBY COMPLETION TIME:")
  for bucket, slice_df in slicer.slice_by_completion_time().items():
    analysis["by_completion_time"][bucket] = len(slice_df)
    print(f"  {bucket}: {len(slice_df)} tickets")

  # By label
  print("\nBY LABEL:")
  for label in ["bug", "enhancement", "crash"]:
    analysis["by_label"][label] = {}
    for name, slice_df in slicer.slice_by_label(label).items():
      analysis["by_label"][label][name] = len(slice_df)
      print(f"  {label}/{name}: {len(slice_df)} tickets")

  print("\nAnalysis complete!")
  return analysis


def generate_bias_report_text(
  detection_analysis: dict, mitigation_results: dict | None = None
) -> str:
  """Generate a formatted text report from bias detection and mitigation results.

  Args:
      detection_analysis: Output from run_bias_detection()
      mitigation_results: Output from run_bias_mitigation_weights() (optional)

  Returns:
      Formatted text report as string
  """
  lines = ["=" * 80]
  lines.append("BIAS ANALYSIS REPORT")
  lines.append("=" * 80)

  # Summary
  lines.append("\nSUMMARY")
  lines.append("-" * 80)
  total_tickets = detection_analysis.get("total_tickets", 0)
  lines.append(f"Total tickets analyzed: {total_tickets:,}")

  # By Repository
  lines.append("\nBY REPOSITORY")
  lines.append("-" * 80)
  for repo, data in detection_analysis.get("by_repository", {}).items():
    count = data.get("count", 0)
    avg_hours = data.get("avg_hours", 0)
    pct = (count / total_tickets * 100) if total_tickets > 0 else 0
    lines.append(
      f"  {repo:30} | Count: {count:5} ({pct:5.1f}%) | Avg Hours: {avg_hours:7.2f}"
    )

  # By Seniority
  lines.append("\nBY SENIORITY")
  lines.append("-" * 80)
  for seniority, data in detection_analysis.get("by_seniority", {}).items():
    count = data.get("count", 0)
    avg_hours = data.get("avg_hours", 0)
    pct = (count / total_tickets * 100) if total_tickets > 0 else 0
    lines.append(
      f"  {seniority:30} | Count: {count:5} ({pct:5.1f}%) | Avg Hours: {avg_hours:7.2f}"
    )

  # By Completion Time
  lines.append("\nBY COMPLETION TIME")
  lines.append("-" * 80)
  for bucket, count in detection_analysis.get("by_completion_time", {}).items():
    pct = (count / total_tickets * 100) if total_tickets > 0 else 0
    lines.append(f"  {bucket:30} | Count: {count:5} ({pct:5.1f}%)")

  # By Label
  lines.append("\nBY LABEL")
  lines.append("-" * 80)
  by_label = detection_analysis.get("by_label", {})
  for label, label_counts in by_label.items():
    for name, count in label_counts.items():
      pct = (count / total_tickets * 100) if total_tickets > 0 else 0
      lines.append(f"  {label}/{name:24} | Count: {count:5} ({pct:5.1f}%)")

  # Mitigation Weights
  if mitigation_results and "weights_by_group" in mitigation_results:
    lines.append("\nMITIGATION SAMPLE WEIGHTS")
    lines.append("-" * 80)
    for group, weight in mitigation_results["weights_by_group"].items():
      lines.append(f"  {group:30} | Weight: {weight:.4f}")

  lines.append("\n" + "=" * 80)
  lines.append("END OF REPORT")
  lines.append("=" * 80)

  return "\n".join(lines)


if __name__ == "__main__":
  default_path = (
    Paths.data_root / "github_issues" / "tickets_transformed_improved.jsonl"
  )
  run_bias_detection(default_path)
