"""Entry point for model training.

Parses CLI arguments, trains each requested model, plots aggregate metrics,
saves best model info, runs sensitivity analysis, logs everything to MLflow
(with nested per-model and per-trial runs), optionally promotes the best model
to the MLflow Model Registry, and pushes artifacts to GCP Cloud Storage.

Environment Variables:
  MLFLOW_TRACKING_URI: MLflow server URL (auto-resolved from GCP if not set).
  MLFLOW_EXPERIMENT_NAME: MLflow experiment name (defaults to "ticket-forge-training").
  MLFLOW_MAX_TUNING_RUNS: Maximum number of hyperparameter tuning runs to log
    (defaults to 50). Reduce for faster iteration during local development.
  TICKET_FORGE_DATASET_ID: Optional dataset ID/path override.
    - If set, uses the specified dataset instead of the latest.
    - Can be a directory name (e.g., 'github_issues-2026-02-24T200000Z')
      or an absolute path.
    - If relative, resolved relative to data_root.
    - Must contain tickets_transformed_improved.jsonl or
      tickets_transformed_improved.jsonl.gz.
"""

import argparse
import datetime
import importlib
import json
import os
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
from shared.configuration import Paths, getenv_or
from shared.logging import get_logger
from training.analysis.mlflow_config import (
  DEFAULT_TRACKING_URI,
  configure_mlflow_from_env,
)
from training.analysis.run_manifest import create_run_manifest, update_manifest
from training.cloud_storage_loader import CloudDatasetReference, resolve_cloud_dataset
from training.dataset import find_latest_pipeline_output

logger = get_logger(__name__)
models = {"forest", "svm", "xgboost", "lgbm"}
models_with_sample_weight = models.difference(set(["svm", "lgbm"]))


def _ensure_run_manifest(run_id: str) -> None:
  """Create run manifest if missing.

  Args:
      run_id: Training run identifier.
  """
  manifest_path = Paths.models_root / run_id / "run_manifest.json"
  if manifest_path.exists():
    return

  create_run_manifest(
    run_id=run_id,
    trigger_type="local",
    commit_sha="",
    snapshot_id="unknown",
    source_uri="unknown",
  )


def persist_validation_gate_outcome(
  run_id: str,
  validation_gate: dict[str, object],
) -> None:
  """Persist validation gate outcome to run manifest and logs.

  Args:
      run_id: Training run identifier.
      validation_gate: Validation gate payload.
  """
  update_manifest(run_id, validation_report=validation_gate)
  logger.info(
    "Validation gate updated in run manifest for %s (passed=%s)",
    run_id,
    validation_gate.get("passed"),
  )


def _parse_arguments(
  argv: list[str] | None = None,
) -> tuple[set[str], str, bool, bool, str | None]:
  """Parse command line arguments.

  Returns:
      Tuple of (models_to_train, run_id, promote)
  """
  parser = argparse.ArgumentParser(
    description=f"utility to train the models. scripts executed with {Paths.repo_root=}"
  )

  parser.add_argument(
    "--models",
    "-m",
    nargs="*",
    type=str,
    help="the models to train, defaults to those which support sample weights",
    choices=models,
    default=models_with_sample_weight,
  )
  parser.add_argument(
    "--runid",
    "-r",
    type=str,
    help="run identifier, defaults to current timestamp",
    default=datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S"),
  )
  parser.add_argument(
    "--promote",
    action="store_true",
    help="promote best model to MLflow Production after training",
  )

  parser.add_argument(
    "--cloud-storage",
    action="store_true",
    help="load dataset location from GCS bucket index.json instead of local data",
  )

  parser.add_argument(
    "--gcs-bucket",
    type=str,
    default=None,
    help="optional gs:// bucket URI override for cloud dataset resolution",
  )

  args = parser.parse_args(argv)
  return args.models, args.runid, args.promote, args.cloud_storage, args.gcs_bucket


def _enable_autolog(max_tuning_runs: int) -> None:
  """Enable sklearn autologging in MLflow for model training.

  Logs metrics and parameters for all tuning runs but does NOT log model
  artifacts (log_models=False) since trainers already persist models locally.
  This significantly speeds up training by avoiding redundant artifact uploads.

  Args:
      max_tuning_runs: Maximum number of tuning runs to capture.
  """
  mlflow.sklearn.autolog(
    log_models=False,
    max_tuning_runs=max_tuning_runs,
    exclusive=False,
    silent=True,
  )


def _train_models(models_list: set[str], run_id: str) -> None:
  """Train all specified models under nested MLflow runs.

  Args:
      models_list: Set of model names to train.
      run_id: Run identifier for saving outputs.
  """
  for model in sorted(models_list):
    start = time.perf_counter()
    success = False
    logger.info("---------- TRAINING %s ----------", model)

    with mlflow.start_run(run_name=f"search_{model}", nested=True):
      mlflow.set_tag("run_level", "model")
      mlflow.set_tag("model_name", model)
      mlflow.set_tag("run_id", run_id)
      mlflow.set_tag("dataset_id", find_latest_pipeline_output())
      try:
        mod = importlib.import_module(f"training.trainers.train_{model}", package="src")
        mod.main(run_id)
        success = True
        mlflow.set_tag("training_status", "succeeded")

        # Log the best model variant for this sub-model type
        run_dir = Paths.models_root / run_id
        model_pkl = run_dir / f"{model}.pkl"
        eval_json = run_dir / f"eval_{model}.json"

        if model_pkl.exists():
          mlflow.log_artifact(str(model_pkl), artifact_path="model")

        if eval_json.exists():
          with open(eval_json) as f:
            metrics = json.load(f)
            for metric_name, metric_value in metrics.items():
              # Only log scalar metrics to MLflow — skip lists/dicts
              if isinstance(metric_value, (int, float)):
                mlflow.log_metric(metric_name, metric_value)
          logger.info(
            "Logged best %s model (macro_f1=%.4f, accuracy=%.4f)",
            model,
            metrics.get("macro_f1", 0),
            metrics.get("accuracy", 0),
          )
      except Exception:
        mlflow.set_tag("training_status", "failed")
        logger.exception("Error training model %s", model)

    train_time = datetime.timedelta(seconds=time.perf_counter() - start)
    msg = "SUCCEEDED" if success else "FAILED"
    logger.info("---------- TRAINING %s %s in (%s) ----------", model, msg, train_time)


def _configure_cloud_dataset(
  run_id: str,
  use_cloud_storage: bool,
  gcs_bucket: str | None,
) -> CloudDatasetReference | None:
  """Resolve cloud dataset inputs and persist source metadata in manifest.

  Args:
      run_id: Training run identifier.
      use_cloud_storage: Whether cloud dataset mode is enabled.
      gcs_bucket: Optional bucket override URI.

  Returns:
      Cloud dataset reference when cloud mode is enabled, otherwise None.
  """
  if not use_cloud_storage:
    return None

  cloud_dataset_ref = resolve_cloud_dataset(gcs_bucket)
  os.environ["TICKET_FORGE_DATASET_ID"] = str(cloud_dataset_ref.local_directory)
  update_manifest(
    run_id,
    data_snapshot={
      "snapshot_id": cloud_dataset_ref.dataset_version,
      "source_uri": cloud_dataset_ref.dataset_uri,
      "resolved_at": datetime.datetime.now(datetime.UTC).isoformat(),
      "dataset_id": cloud_dataset_ref.dataset_id,
      "bucket_name": cloud_dataset_ref.bucket_name,
      "dataset_source": "cloud_storage",
    },
  )
  logger.info(
    "Training configured to use cloud dataset %s (%s)",
    cloud_dataset_ref.dataset_uri,
    cloud_dataset_ref.dataset_version,
  )
  return cloud_dataset_ref


def _load_metrics(run_dir: Path) -> tuple[dict[str, dict[str, float]], list]:
  """Load metrics from all evaluation files in the run directory.

  Args:
      run_dir: Directory containing eval_*.json files

  Returns:
      Tuple of (metrics_data, best_models) where best_models is sorted by macro_f1
  """
  metrics_data = {}
  best_models = []

  for eval_file in run_dir.glob("eval_*.json"):
    model_name = eval_file.stem.replace("eval_", "")
    with open(eval_file) as f:
      metrics_data[model_name] = json.load(f)

      # Track best model by macro_f1 (highest is best)
      if "macro_f1" in metrics_data[model_name]:
        best_models.append(
          (model_name, metrics_data[model_name]["macro_f1"], metrics_data[model_name])
        )

  return metrics_data, best_models


def _save_best_model_info(best_models: list, run_dir: Path) -> None:
  """Save information about the best model to best.txt.

  Args:
      best_models: List of (model_name, macro_f1_score, metrics) tuples
      run_dir: Directory to save best.txt to
  """
  if not best_models:
    return

  best_models.sort(key=lambda x: x[1], reverse=True)
  best_model_name = best_models[0][0]
  best_model_score = best_models[0][1]

  best_file = run_dir / "best.txt"
  with open(best_file, "w") as f:
    f.write(f"Best Model: {best_model_name}\n")
    f.write(f"Macro F1 Score: {best_model_score:.4f}\n")
    f.write("\nAll Metrics:\n")
    for key, value in best_models[0][2].items():
      # Only write scalar metrics — skip confusion_matrix and classification_report
      if isinstance(value, (int, float)):
        f.write(f"{key}: {value:.4f}\n")

  logger.info("=" * 50)
  logger.info("Best model: %s (Macro F1: %.4f)", best_model_name, best_model_score)
  logger.info("Results saved to %s", best_file)
  logger.info("=" * 50)


def _run_mlflow_training_pipeline(
  models_list: set[str],
  run_id: str,
  run_dir: Path,
) -> None:
  """Run the multi-model training workflow under a parent MLflow run.

  Args:
      models_list: Set of model names to train.
      run_id: Unique run identifier.
      run_dir: Directory where run artifacts are stored.
  """
  with mlflow.start_run(run_name="multi_model_search"):
    mlflow.set_tag("run_level", "parent")
    mlflow.set_tag("run_id", run_id)
    mlflow.log_params(
      {
        "run_id": run_id,
        "candidate_models": ",".join(sorted(models_list)),
        "candidate_model_count": len(models_list),
      }
    )

    _train_models(models_list, run_id)

    metrics_data, best_models = _load_metrics(run_dir)
    if metrics_data:
      _plot_metrics(metrics_data, run_dir)
      perf_plot = run_dir / "performance.png"
      if perf_plot.exists():
        mlflow.log_artifact(str(perf_plot), artifact_path="plots")

    _save_best_model_info(best_models, run_dir)
    best_file = run_dir / "best.txt"
    if best_file.exists():
      mlflow.log_artifact(str(best_file), artifact_path="summary")

    try:
      from training.analysis.run_sensitivity_analysis import (
        run_sensitivity_analysis,
        save_cv_results,
      )

      save_cv_results(run_id)
      run_sensitivity_analysis(run_id)
    except Exception:
      logger.exception("Sensitivity analysis failed — skipping")


def _run_post_training_actions(run_id: str, promote: bool) -> None:
  """Run optional promotion and artifact push logic.

  Args:
      run_id: Unique run identifier.
      promote: Whether model promotion should be attempted.
  """
  if promote:
    from training.analysis.mlflow_tracking import promote_best_model

    promote_best_model(run_id)

  try:
    from training.analysis.push_model_artifact import push_model_artifacts

    push_model_artifacts(run_id)
  except Exception:
    logger.exception("Artifact push failed — skipping")


def main() -> None:
  """Trains models according to user params."""
  models_list, run_id, promote, use_cloud_storage, gcs_bucket = _parse_arguments()

  # Create output directory for this run
  run_dir = Paths.models_root / run_id
  run_dir.mkdir(parents=True, exist_ok=True)
  _ensure_run_manifest(run_id)

  cloud_dataset_ref = _configure_cloud_dataset(
    run_id=run_id,
    use_cloud_storage=use_cloud_storage,
    gcs_bucket=gcs_bucket,
  )

  tracking_uri = configure_mlflow_from_env(DEFAULT_TRACKING_URI)
  experiment_name = str(getenv_or("MLFLOW_EXPERIMENT_NAME", "ticket-forge-training"))
  max_tuning_runs = 5
  max_tuning_runs_env = getenv_or("MLFLOW_MAX_TUNING_RUNS")
  if max_tuning_runs_env:
    try:
      max_tuning_runs = int(max_tuning_runs_env)
    except ValueError:
      msg = f"Invalid MLFLOW_MAX_TUNING_RUNS: {max_tuning_runs_env}. Using default 50."
      logger.warning(msg)

  mlflow.set_experiment(experiment_name)
  _enable_autolog(max_tuning_runs=max_tuning_runs)
  logger.info("MLflow configured for training harness: %s", tracking_uri)
  logger.info("Max tuning runs to log: %d", max_tuning_runs)

  _run_mlflow_training_pipeline(models_list=models_list, run_id=run_id, run_dir=run_dir)
  _run_post_training_actions(run_id=run_id, promote=promote)

  if cloud_dataset_ref is not None:
    update_manifest(
      run_id,
      training_dataset={
        "dataset_source": "cloud_storage",
        "dataset_path": cloud_dataset_ref.dataset_uri,
        "dataset_version": cloud_dataset_ref.dataset_version,
        "dataset_id": cloud_dataset_ref.dataset_id,
      },
    )


def _plot_metrics(metrics_data: dict[str, dict[str, float]], run_dir: Path) -> None:
  """Plot model metrics and save as performance.png.

  Args:
      metrics_data: Dictionary of model names to their metrics
      run_dir: Directory to save the plot to
  """
  model_names = list(metrics_data.keys())
  metric_keys = ["accuracy", "macro_f1", "macro_precision", "macro_recall"]

  # Create subplots for different metrics
  fig, axes = plt.subplots(2, 2, figsize=(12, 10))
  fig.suptitle("Model Performance Comparison", fontsize=16)

  for idx, metric in enumerate(metric_keys):
    ax = axes[idx // 2, idx % 2]
    values = [metrics_data[model].get(metric, 0) for model in model_names]

    colors = plt.get_cmap("viridis")(  # type: ignore
      [i / len(model_names) for i in range(len(model_names))]
    )
    ax.bar(model_names, values, color=colors)
    ax.set_ylabel(metric.upper())
    ax.set_title(f"{metric.upper()} by Model")
    ax.set_ylim(0, 1)
    ax.grid(axis="y", alpha=0.3)
    ax.tick_params(axis="x", rotation=45)

  plt.tight_layout()

  plot_file = run_dir / "performance.png"
  plt.savefig(plot_file, dpi=100, bbox_inches="tight")
  logger.info("Performance plot saved to %s", plot_file)
  plt.close()


if __name__ == "__main__":
  main()
