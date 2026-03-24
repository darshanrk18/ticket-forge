"""Shared fixtures for model CI/CD gate tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_candidate_metrics() -> dict[str, float]:
  """Return representative candidate metrics for gate checks."""
  return {"mae": 4.2, "rmse": 6.1, "r2": 0.91}


@pytest.fixture
def sample_baseline_metrics() -> dict[str, float]:
  """Return representative baseline metrics for guardrail checks."""
  return {"mae": 4.0, "rmse": 5.8, "r2": 0.92}


@pytest.fixture
def sample_gate_report(tmp_path: Path) -> Path:
  """Create a sample gate report JSON file and return its path."""
  report = {
    "run_id": "run-1",
    "candidate_model": "forest",
    "validation_gate": {"passed": True, "metrics": {}, "thresholds": {}},
    "bias_gate": {"passed": True, "slices_evaluated": []},
    "regression_guardrail": {
      "passed": True,
      "max_allowed_degradation": 0.1,
      "metric_deltas": {},
    },
    "promotion_decision": {"decision": "promoted", "promoted": True},
    "generated_at": "2026-03-23T00:00:00+00:00",
  }
  path = tmp_path / "gate_report.json"
  path.write_text(json.dumps(report), encoding="utf-8")
  return path
