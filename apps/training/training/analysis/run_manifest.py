"""Run manifest helpers for model CI/CD artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from shared.configuration import Paths
from shared.logging import get_logger

logger = get_logger(__name__)


def _manifest_path(run_id: str) -> Path:
  """Return the run manifest path for a training run."""
  run_dir = Paths.models_root / run_id
  run_dir.mkdir(parents=True, exist_ok=True)
  return run_dir / "run_manifest.json"


def create_run_manifest(
  run_id: str,
  trigger_type: str,
  commit_sha: str,
  snapshot_id: str,
  source_uri: str,
) -> Path:
  """Create a run manifest with initial pipeline state.

  Args:
      run_id: CI run identifier.
      trigger_type: Workflow trigger source.
      commit_sha: Source commit SHA.
      snapshot_id: Data snapshot identifier.
      source_uri: Data source URI.

  Returns:
      Path to created run manifest file.
  """
  manifest = {
    "pipeline_run": {
      "run_id": run_id,
      "trigger_type": trigger_type,
      "commit_sha": commit_sha,
      "started_at": datetime.now(tz=UTC).isoformat(),
      "status": "running",
      "promoted": False,
      "skip_reason": None,
    },
    "data_snapshot": {
      "snapshot_id": snapshot_id,
      "source_uri": source_uri,
      "resolved_at": datetime.now(tz=UTC).isoformat(),
      "is_approved": True,
    },
    "model_candidate": None,
    "validation_report": None,
    "bias_report": None,
    "baseline_comparison": None,
    "promotion_decision": None,
    "notifications": [],
  }

  path = _manifest_path(run_id)
  with open(path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
  logger.info("Created run manifest at %s", path)
  return path


def load_manifest(run_id: str) -> dict[str, object]:
  """Load an existing run manifest.

  Args:
      run_id: CI run identifier.

  Returns:
      Parsed run manifest dictionary.
  """
  path = _manifest_path(run_id)
  with open(path, encoding="utf-8") as f:
    return json.load(f)


def update_manifest(run_id: str, **sections: object) -> Path:
  """Update one or more top-level sections in the run manifest.

  Args:
      run_id: CI run identifier.
      **sections: Named sections to replace in the manifest.

  Returns:
      Path to updated manifest file.
  """
  path = _manifest_path(run_id)
  manifest = load_manifest(run_id) if path.exists() else {}

  for key, value in sections.items():
    manifest[key] = value

  raw_pipeline = manifest.get("pipeline_run", {})
  pipeline = raw_pipeline if isinstance(raw_pipeline, dict) else {}
  pipeline.setdefault("run_id", run_id)
  manifest["pipeline_run"] = pipeline

  with open(path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)

  logger.info("Updated run manifest at %s", path)
  return path
