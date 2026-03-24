"""Push best model artifacts to GCP Cloud Storage.

Reads best.txt from the given run directory to identify the best model,
then uploads the following artifacts to gs://ticketforge-dvc/models/{run_id}/:

  - {model}.pkl          : joblib model pickle
  - eval_{model}.json    : test set metrics (MAE, MSE, RMSE, R2)
  - bias_{model}_*.txt   : bias detection reports for all sensitive features

The GCS path mirrors the local models/{run_id}/ directory structure so
artifacts are easy to locate and download for serving or auditing.

Prerequisites:
  - gcloud auth application-default login
  - google-cloud-storage installed (included in training dependencies)

Usage:
  python -m training.analysis.push_model_artifact --runid 2026-03-20_184819
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from shared.configuration import Paths, getenv_or
from shared.logging import get_logger

try:
  from google.cloud import storage  # type: ignore[import]

  HAS_GCS = True
except ImportError:
  HAS_GCS = False
  storage = None  # type: ignore[assignment]

logger = get_logger(__name__)

# GCS bucket name — same bucket used by DVC for data versioning.
_DEFAULT_BUCKET = "ticketforge-dvc"
# GCS prefix under which all model artifacts are stored.
_GCS_MODELS_PREFIX = "models"


def _read_best_model(run_dir: Path) -> str | None:
  """Read the best model name from best.txt.

  Args:
      run_dir: Path to the training run directory.

  Returns:
      Model name string (e.g. 'random_forest'), or None if best.txt missing.
  """
  best_file = run_dir / "best.txt"
  if not best_file.exists():
    logger.warning("best.txt not found in %s", run_dir)
    return None

  with open(best_file) as f:
    for line in f:
      if line.startswith("Best Model:"):
        return line.replace("Best Model:", "").strip()

  logger.warning("Could not parse best model name from %s", best_file)
  return None


def _collect_artifacts(run_dir: Path, model_name: str) -> list[Path]:
  """Collect all artifact files to upload for the best model.

  Includes the model pickle, eval metrics JSON, and all bias report
  text files for the model.

  Args:
      run_dir:    Path to the training run directory.
      model_name: Name of the best model (e.g. 'random_forest').

  Returns:
      List of existing file paths to upload.
  """
  candidates = [
    run_dir / f"{model_name}.pkl",
    run_dir / f"eval_{model_name}.json",
    run_dir / "performance.png",
    run_dir / "best.txt",
    run_dir / "gate_report.json",
    run_dir / "run_manifest.json",
    *run_dir.glob(f"bias_{model_name}_*.txt"),
    *run_dir.glob(f"hyperparam_sensitivity_{model_name}.png"),
    *run_dir.glob(f"shap_importance_{model_name}.png"),
  ]
  artifacts = [p for p in candidates if p.exists()]

  missing = [p for p in candidates[:2] if not p.exists()]
  for p in missing:
    logger.warning("Expected artifact not found: %s", p)

  return artifacts


def push_model_artifacts(
  run_id: str,
  bucket_name: str = _DEFAULT_BUCKET,
  dry_run: bool = False,
) -> list[str]:
  """Push best model artifacts to GCP Cloud Storage.

  Identifies the best model from best.txt, collects its artifacts,
  and uploads them to gs://{bucket}/{models_prefix}/{run_id}/.

  Args:
      run_id:      Training run identifier (subdirectory under models_root).
      bucket_name: GCS bucket name to upload to.
      dry_run:     If True, log what would be uploaded without actually
                   uploading. Useful for testing without GCP credentials.

  Returns:
      List of GCS URIs that were uploaded (or would be uploaded in dry_run).

  Raises:
      FileNotFoundError: If the run directory does not exist.
      RuntimeError:      If no best model can be determined.
  """
  run_dir = Paths.models_root / run_id
  if not run_dir.exists():
    msg = f"Run directory not found: {run_dir}"
    raise FileNotFoundError(msg)

  model_name = _read_best_model(run_dir)
  if model_name is None:
    msg = f"Could not determine best model for run {run_id}"
    raise RuntimeError(msg)

  logger.info("Best model for run %s: %s", run_id, model_name)

  artifacts = _collect_artifacts(run_dir, model_name)
  if not artifacts:
    logger.warning("No artifacts found to upload for %s", model_name)
    return []

  gcs_uris: list[str] = []

  if not dry_run:
    if not HAS_GCS:
      logger.warning(
        "google-cloud-storage not installed. Run: uv add google-cloud-storage"
      )
      return []

    client = storage.Client()
    bucket = client.bucket(bucket_name)

  for artifact_path in artifacts:
    gcs_blob_name = f"{_GCS_MODELS_PREFIX}/{run_id}/{artifact_path.name}"
    gcs_uri = f"gs://{bucket_name}/{gcs_blob_name}"
    gcs_uris.append(gcs_uri)

    if dry_run:
      logger.info("[dry-run] Would upload %s -> %s", artifact_path, gcs_uri)
      continue

    blob = bucket.blob(gcs_blob_name)
    blob.upload_from_filename(str(artifact_path))
    logger.info("Uploaded %s -> %s", artifact_path.name, gcs_uri)

  if not dry_run:
    _write_artifact_manifest(run_dir, model_name, gcs_uris, bucket_name, run_id)

  logger.info(
    "Successfully pushed %d artifacts for %s to gs://%s/%s/%s/",
    len(gcs_uris),
    model_name,
    bucket_name,
    _GCS_MODELS_PREFIX,
    run_id,
  )
  return gcs_uris


def _write_artifact_manifest(
  run_dir: Path,
  model_name: str,
  gcs_uris: list[str],
  bucket_name: str,
  run_id: str,
) -> None:
  """Write a manifest JSON file recording what was pushed and where.

  Args:
      run_dir:     Local run directory to save the manifest in.
      model_name:  Best model name.
      gcs_uris:    List of GCS URIs that were uploaded.
      bucket_name: GCS bucket name.
      run_id:      Training run identifier.
  """
  manifest = {
    "run_id": run_id,
    "best_model": model_name,
    "bucket": bucket_name,
    "gcs_prefix": f"gs://{bucket_name}/{_GCS_MODELS_PREFIX}/{run_id}/",
    "artifacts": gcs_uris,
  }
  manifest_path = run_dir / "artifact_manifest.json"
  with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2)
  logger.info("Artifact manifest saved to %s", manifest_path)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    description="Push best model artifacts to GCP Cloud Storage."
  )
  parser.add_argument(
    "--runid",
    "-r",
    required=True,
    help="Run ID (subdirectory under models/)",
  )
  parser.add_argument(
    "--bucket",
    "-b",
    default=getenv_or("GCS_BUCKET", _DEFAULT_BUCKET),
    help="GCS bucket name (default: ticketforge-dvc)",
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Log what would be uploaded without actually uploading",
  )
  args = parser.parse_args()
  push_model_artifacts(args.runid, args.bucket, args.dry_run)
