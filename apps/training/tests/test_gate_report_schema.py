"""Tests that gate reports contain required contract fields."""

from training.analysis.gate_report import build_gate_report

REQUIRED_FIELDS = {
  "run_id",
  "candidate_model",
  "validation_gate",
  "bias_gate",
  "regression_guardrail",
  "promotion_decision",
  "generated_at",
}


def test_gate_report_has_required_top_level_fields() -> None:
  """Built gate report includes all required schema keys."""
  report = build_gate_report(
    run_id="run-1",
    candidate_model="forest",
    gate_sections={
      "validation_gate": {"passed": True, "metrics": {}, "thresholds": {}},
      "bias_gate": {"passed": True, "slices_evaluated": []},
      "regression_guardrail": {
        "passed": True,
        "max_allowed_degradation": 0.1,
        "metric_deltas": {},
      },
    },
    promotion_decision={"decision": "promoted", "promoted": True},
  )

  assert REQUIRED_FIELDS.issubset(set(report.keys()))
