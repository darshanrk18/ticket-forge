"""Tests for bias gate decision layer."""

from __future__ import annotations

from pathlib import Path

from training.analysis.bias_gate import evaluate_bias_gate
from training.analysis.gate_config import GateConfig


def test_bias_gate_fails_when_report_marks_bias(tmp_path: Path) -> None:
  """Bias gate fails when report explicitly indicates bias detected."""
  report = tmp_path / "bias_forest_repo.txt"
  report.write_text("bias_detected: true\nrelative_gap: 0.2\n", encoding="utf-8")

  result = evaluate_bias_gate(tmp_path, "forest", GateConfig())
  assert result["passed"] is False
  assert any("bias-detected" in r for r in result["fail_reasons"])


def test_bias_gate_fails_when_relative_gap_exceeds_threshold(tmp_path: Path) -> None:
  """Bias gate fails when relative gap exceeds configured threshold."""
  report = tmp_path / "bias_forest_repo.txt"
  report.write_text("relative_gap: 0.9\n", encoding="utf-8")

  result = evaluate_bias_gate(
    tmp_path,
    "forest",
    GateConfig(max_bias_relative_gap=0.4),
  )
  assert result["passed"] is False


def test_bias_gate_fails_closed_when_reports_missing(tmp_path: Path) -> None:
  """Bias gate fails closed if expected reports are missing."""
  result = evaluate_bias_gate(tmp_path, "forest", GateConfig())
  assert result["passed"] is False
  assert "missing-bias-reports" in result["fail_reasons"]
