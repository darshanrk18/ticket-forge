"""CI entrypoint to train, evaluate gates, and optionally promote a model."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shared.configuration import Paths
from shared.logging import get_logger
from training.analysis.bias_gate import evaluate_bias_gate
from training.analysis.gate_config import load_gate_config
from training.analysis.gate_report import build_gate_report, write_gate_report
from training.analysis.mlflow_config import (
  DEFAULT_TRACKING_URI,
  configure_mlflow_from_env,
)
from training.analysis.regression_guardrail import evaluate_regression_guardrail
from training.analysis.run_manifest import (
  create_run_manifest,
  load_manifest,
  update_manifest,
)
from training.analysis.validation_gate import evaluate_validation_gate

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
  """Parse CLI arguments for CI gate runner."""
  parser = argparse.ArgumentParser(description="Run training + gate checks in CI")
  parser.add_argument("--runid", required=True, help="Run identifier")
  parser.add_argument("--trigger", default="push", help="Trigger type")
  parser.add_argument(
    "--commit-sha", default=_get_git_commit_sha() or "", help="Commit SHA"
  )
  parser.add_argument("--snapshot-id", default="dvc-latest", help="DVC snapshot id")
  parser.add_argument("--source-uri", default="dvc://data", help="Dataset source URI")
  parser.add_argument(
    "--promote",
    choices=["true", "false"],
    default="true",
    help="Whether to promote when gates pass",
  )
  return parser.parse_args()


def _get_git_commit_sha() -> str | None:
  try:
    # Run the git command to get the full SHA of the current HEAD
    result = subprocess.run(
      ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()
  except subprocess.CalledProcessError:
    logger.exception("Error running git command")
    return None
  except FileNotFoundError:
    logger.exception("Git is not installed or not in PATH.")
    return None


def _run_training(run_id: str) -> None:
  """Execute model training command for a given run id."""
  cmd = [sys.executable, "-m", "training.cmd.train", "--runid", run_id]
  logger.info("Running training command: %s", " ".join(cmd))
  subprocess.run(cmd, check=True)


def _read_best_model(run_dir: Path) -> str:
  """Read best model name from best.txt.

  Args:
      run_dir: Model run directory.

  Returns:
      Best model name.
  """
  best_file = run_dir / "best.txt"
  if not best_file.exists():
    msg = f"Missing best model file at {best_file}"
    raise FileNotFoundError(msg)

  for line in best_file.read_text(encoding="utf-8").splitlines():
    if line.startswith("Best Model:"):
      return line.replace("Best Model:", "").strip()

  msg = f"Could not parse best model in {best_file}"
  raise RuntimeError(msg)


def _read_eval_metrics(run_dir: Path, model_name: str) -> dict[str, float]:
  """Read evaluation metrics for a model.

  Args:
      run_dir: Model run directory.
      model_name: Model identifier.

  Returns:
      Metrics dictionary.
  """
  eval_path = run_dir / f"eval_{model_name}.json"
  if not eval_path.exists():
    msg = f"Missing eval metrics file at {eval_path}"
    raise FileNotFoundError(msg)

  with open(eval_path, encoding="utf-8") as f:
    raw = json.load(f)
  return {k: float(v) for k, v in raw.items() if isinstance(v, int | float)}


def _load_production_baseline() -> tuple[str | None, dict[str, float] | None]:
  """Load production baseline metrics from MLflow registry run, if available."""
  try:
    from mlflow.tracking import MlflowClient  # type: ignore[import]
  except Exception:
    logger.warning("MLflow unavailable; skipping baseline comparison")
    return None, None

  client = MlflowClient()
  try:
    versions = client.get_latest_versions("ticket-forge-best", stages=["Production"])
  except Exception:
    logger.warning("Unable to fetch production versions from MLflow")
    return None, None

  if not versions:
    return None, None

  version = versions[0]
  run_metrics = client.get_run(version.run_id).data.metrics
  baseline_metrics: dict[str, float] = {}
  for key in ("eval_mae", "eval_rmse", "eval_r2", "mae", "rmse", "r2"):
    if key in run_metrics:
      normalized = key.replace("eval_", "")
      baseline_metrics[normalized] = float(run_metrics[key])

  return str(version.version), baseline_metrics or None


def main() -> int:
  """Run CI model workflow and return process exit code."""
  args = _parse_args()
  configure_mlflow_from_env(DEFAULT_TRACKING_URI)

  run_id = args.runid
  run_dir: Path = Paths.models_root / run_id

  create_run_manifest(
    run_id=run_id,
    trigger_type=args.trigger,
    commit_sha=args.commit_sha,
    snapshot_id=args.snapshot_id,
    source_uri=args.source_uri,
  )

  if run_dir.exists():
    logger.warning("RUN_ID already exists, skipping training")
  else:
    _run_training(run_id)

  best_model = _read_best_model(run_dir)
  candidate_metrics = _read_eval_metrics(run_dir, best_model)
  config = load_gate_config()

  validation_gate = evaluate_validation_gate(candidate_metrics, config)
  bias_gate = evaluate_bias_gate(run_dir, best_model, config)

  baseline_version, baseline_metrics = _load_production_baseline()
  regression_guardrail = evaluate_regression_guardrail(
    candidate_metrics,
    baseline_metrics,
    config.max_regression_degradation,
  )

  should_promote = args.promote == "true"
  gates_passed = (
    validation_gate["passed"] and bias_gate["passed"] and regression_guardrail["passed"]
  )

  promotion_decision: dict[str, Any] = {
    "decision": "skipped",
    "promoted": False,
    "promoted_model_version": None,
    "reasons": [],
  }

  if not gates_passed:
    reasons = (
      validation_gate.get("fail_reasons", [])
      + bias_gate.get("fail_reasons", [])
      + regression_guardrail.get("fail_reasons", [])
    )
    promotion_decision = {
      "decision": "blocked",
      "promoted": False,
      "promoted_model_version": None,
      "reasons": reasons,
    }
  elif should_promote:
    from training.analysis.mlflow_tracking import promote_best_model

    promoted_version = promote_best_model(run_id)
    if promoted_version:
      promotion_decision = {
        "decision": "promoted",
        "promoted": True,
        "promoted_model_version": promoted_version,
        "reasons": [],
      }
    else:
      promotion_decision = {
        "decision": "failed",
        "promoted": False,
        "promoted_model_version": None,
        "reasons": ["promotion-failed"],
      }

  report = build_gate_report(
    run_id=run_id,
    candidate_model=best_model,
    gate_sections={
      "validation_gate": validation_gate,
      "bias_gate": bias_gate,
      "regression_guardrail": regression_guardrail,
    },
    baseline_model_version=baseline_version,
    promotion_decision=promotion_decision,
  )
  report_path = write_gate_report(run_id, report)

  update_manifest(
    run_id,
    model_candidate={
      "candidate_id": f"{run_id}:{best_model}",
      "run_id": run_id,
      "model_name": best_model,
      "artifact_path": str(run_dir / f"{best_model}.pkl"),
      "training_params": {},
      "tracking_run_id": run_id,
      "created_at": datetime.now(tz=UTC).isoformat(),
    },
    validation_report={
      "report_id": f"validation:{run_id}",
      "run_id": run_id,
      "candidate_id": f"{run_id}:{best_model}",
      **validation_gate,
      "generated_at": datetime.now(tz=UTC).isoformat(),
    },
    bias_report={
      "report_id": f"bias:{run_id}",
      "run_id": run_id,
      "candidate_id": f"{run_id}:{best_model}",
      **bias_gate,
      "generated_at": datetime.now(tz=UTC).isoformat(),
    },
    baseline_comparison={
      "comparison_id": f"baseline:{run_id}",
      "run_id": run_id,
      "candidate_id": f"{run_id}:{best_model}",
      "baseline_model_version": baseline_version,
      **regression_guardrail,
    },
    promotion_decision={
      "decision_id": f"promotion:{run_id}",
      "run_id": run_id,
      "candidate_id": f"{run_id}:{best_model}",
      **promotion_decision,
      "baseline_retained": not promotion_decision["promoted"],
      "decided_at": datetime.now(tz=UTC).isoformat(),
    },
    pipeline_run={
      "run_id": run_id,
      "trigger_type": args.trigger,
      "commit_sha": args.commit_sha,
      "status": (
        "success"
        if promotion_decision["decision"] in {"promoted", "skipped"}
        else "blocked"
      ),
      "completed_at": datetime.now(tz=UTC).isoformat(),
      "promoted": bool(promotion_decision["promoted"]),
      "skip_reason": None,
    },
  )

  logger.info("Gate report written to %s", report_path)
  manifest = load_manifest(run_id)
  logger.info(f"Manifest: {json.dumps(manifest, indent=2)}")

  if promotion_decision["decision"] in {"blocked", "failed"}:
    logger.critical(f"failed to promote! {json.dumps(promotion_decision, indent=2)}")
    return 2
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
