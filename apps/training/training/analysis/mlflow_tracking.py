"""MLflow experiment tracking and model promotion for ticket-forge training runs.

Provides two main entry points:

  log_run_to_mlflow(run_id)
      Called after training completes. Creates a parent MLflow run for the
      training run, logs per-model test metrics as top-level metrics, and
      creates one nested child run per model that logs every hyperparameter
      trial from cv_results_{model}.json so the trial-level view in the
      MLflow UI matches the screenshot in issue #78.

  promote_best_model(run_id)
      Reads best.txt to identify the best model, registers the model pickle
      as a new version in the MLflow Model Registry under the name
      "ticket-forge-best", and transitions it to the "Production" stage
      (archiving any previous Production version).

MLflow backend defaults to a local filesystem URI (mlruns/ under repo root)
so no running MLflow server is required. Set MLFLOW_TRACKING_URI to point at
a remote server when running in CI/CD.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
from shared.configuration import TRAIN_USE_DUMMY_DATA, Paths
from shared.logging import get_logger
from training.analysis.gate_config import load_gate_config
from training.analysis.mlflow_config import (
  DEFAULT_TRACKING_URI,
  configure_mlflow_from_env,
)
from training.analysis.regression_guardrail import evaluate_regression_guardrail

logger = get_logger(__name__)

_EXPERIMENT_NAME = "ticket-forge-training"
_REGISTERED_MODEL_NAME = "ticket-forge-best"


def _setup_experiment() -> str:
  """Ensure the MLflow experiment exists and return its ID.

  Returns:
      MLflow experiment ID string.
  """
  configure_mlflow_from_env(DEFAULT_TRACKING_URI)

  experiment = mlflow.get_experiment_by_name(_EXPERIMENT_NAME)
  if experiment is None:
    experiment_id = mlflow.create_experiment(_EXPERIMENT_NAME)
  else:
    experiment_id = experiment.experiment_id
  mlflow.set_experiment(_EXPERIMENT_NAME)
  return experiment_id


def _log_trial_runs(
  parent_run_id: str,
  model_name: str,
  cv_results_path: Path,
) -> None:
  """Log each hyperparam trial as a nested child run under parent_run_id.

  Reads cv_results_{model}.json and creates one child MLflow run per trial
  row, logging its hyperparams and mean_test_score so every trial appears
  in the MLflow UI under the parent run (matching the screenshot in #78).

  Args:
      parent_run_id:    MLflow run ID of the parent model-type run.
      model_name:       Model identifier (e.g. "xgboost").
      cv_results_path:  Path to cv_results_{model}.json.
  """
  if not cv_results_path.exists():
    logger.warning(
      "cv_results not found at %s — skipping trial logging for %s",
      cv_results_path,
      model_name,
    )
    return

  with open(cv_results_path) as f:
    cv_results: dict = json.load(f)

  param_keys = [k for k in cv_results if k.startswith("param_")]
  n_trials = len(cv_results.get("mean_test_score", []))

  logger.info(
    "Logging %d hyperparam trials for %s as nested runs", n_trials, model_name
  )

  for i in range(n_trials):
    trial_params: dict[str, str] = {}
    for pk in param_keys:
      val = cv_results[pk][i]
      trial_params[pk.replace("param_", "")] = str(val)

    mean_test_score = cv_results["mean_test_score"][i]
    rank_list = cv_results.get("rank_test_score", [None] * n_trials)
    rank = rank_list[i]

    with mlflow.start_run(
      run_name=f"{model_name}_trial_{i:03d}",
      nested=True,
      tags={
        "mlflow.parentRunId": parent_run_id,
        "model": model_name,
        "trial_index": str(i),
      },
    ):
      mlflow.log_params(trial_params)
      # sklearn scores with neg_mean_squared_error — store both forms
      mlflow.log_metric("mean_test_score", mean_test_score)
      mlflow.log_metric("cv_mse", -mean_test_score)
      if rank is not None:
        mlflow.log_metric("rank", float(rank))


def _log_model_run(
  parent_run_id: str,
  run_id: str,
  model_name: str,
  run_dir: Path,
) -> str:
  """Log one model type as a nested run with test metrics and artifacts.

  Creates a child run under parent_run_id, logs test metrics from
  eval_{model}.json, logs bias reports as text artifacts, logs the best
  CV score, and logs the model pickle via mlflow.sklearn.

  Args:
      parent_run_id:  MLflow run ID of the top-level multi_model_search run.
      run_id:         Training run identifier.
      model_name:     Model identifier (e.g. "forest").
      run_dir:        Local run directory path.

  Returns:
      MLflow run ID of the created child run.
  """
  eval_path = run_dir / f"eval_{model_name}.json"
  pkl_path = run_dir / f"{model_name}.pkl"
  cv_results_path = run_dir / f"cv_results_{model_name}.json"

  with mlflow.start_run(
    run_name=f"search_{model_name}",
    nested=True,
    tags={
      "mlflow.parentRunId": parent_run_id,
      "model": model_name,
      "run_id": run_id,
    },
  ) as model_run:
    model_run_id = model_run.info.run_id

    # Log test set metrics
    if eval_path.exists():
      with open(eval_path) as f:
        metrics: dict[str, float] = json.load(f)
      mlflow.log_metrics(metrics)
      logger.info("Logged test metrics for %s: %s", model_name, metrics)
    else:
      logger.warning("eval_%s.json not found — skipping metric logging", model_name)

    # Log best CV score from cv_results
    if cv_results_path.exists():
      with open(cv_results_path) as f:
        cv_results = json.load(f)
      scores = cv_results.get("mean_test_score", [])
      if scores:
        mlflow.log_metric("best_cv_score", max(scores))

    # Log bias report files as text artifacts
    for bias_file in run_dir.glob(f"bias_{model_name}_*.txt"):
      mlflow.log_artifact(str(bias_file), artifact_path="bias_reports")

    # Log sensitivity analysis plots if present
    for plot_name in (
      f"hyperparam_sensitivity_{model_name}.png",
      f"shap_importance_{model_name}.png",
    ):
      plot_path = run_dir / plot_name
      if plot_path.exists():
        mlflow.log_artifact(str(plot_path), artifact_path="plots")

    # Log model pickle if available
    if pkl_path.exists():
      try:
        grid = joblib.load(pkl_path)
        mlflow.sklearn.log_model(
          grid.best_estimator_,
          artifact_path="best_estimator",
          registered_model_name=None,
        )
        mlflow.log_params({k: str(v) for k, v in (grid.best_params_ or {}).items()})
      except Exception:
        logger.warning(
          "Could not log model pickle for %s — skipping", model_name, exc_info=True
        )

    # Must stay inside this context so nested=True correctly parents trials
    # under search_{model}, not under the top-level multi_model_search run.
    _log_trial_runs(model_run_id, model_name, cv_results_path)

  return model_run_id


def log_run_to_mlflow(run_id: str) -> str | None:
  """Log a completed training run to MLflow.

  Creates a top-level "multi_model_search" parent run and one nested child
  run per trained model. Each model child run logs test metrics, bias
  reports, best CV score, and the model pickle. Under each model child run,
  every CV hyperparam trial is logged as a further nested run so they all
  appear in the MLflow UI.

  Uses a local filesystem backend by default (no server required).
  Set MLFLOW_TRACKING_URI to point at a remote server for CI/CD.

  Args:
      run_id: Training run identifier (subdirectory under models_root).

  Returns:
      MLflow parent run ID, or None if skipped/failed.
  """
  if TRAIN_USE_DUMMY_DATA:
    logger.info("TRAIN_USE_DUMMY_DATA=True — skipping MLflow logging")
    return None

  run_dir = Paths.models_root / run_id
  if not run_dir.exists():
    logger.warning("Run directory %s not found — skipping MLflow logging", run_dir)
    return None

  _setup_experiment()

  model_pkls = list(run_dir.glob("*.pkl"))
  if not model_pkls:
    logger.warning("No model pickles in %s — nothing to log", run_dir)
    return None

  parent_run_mlflow_id: str | None = None

  try:
    with mlflow.start_run(run_name="multi_model_search") as parent_run:
      parent_run_mlflow_id = parent_run.info.run_id
      mlflow.set_tag("run_id", run_id)
      mlflow.set_tag("num_models", str(len(model_pkls)))

      perf_plot = run_dir / "performance.png"
      if perf_plot.exists():
        mlflow.log_artifact(str(perf_plot), artifact_path="plots")

      best_file = run_dir / "best.txt"
      if best_file.exists():
        mlflow.log_artifact(str(best_file), artifact_path="summary")

      for pkl_path in model_pkls:
        model_name = pkl_path.stem
        _log_model_run(parent_run_mlflow_id, run_id, model_name, run_dir)

    logger.info("MLflow logging complete — parent run ID: %s", parent_run_mlflow_id)

  except Exception:
    logger.exception("MLflow logging failed for run %s", run_id)
    return None

  return parent_run_mlflow_id


def _read_best_model_name(run_dir: Path) -> str | None:
  """Read and return the best model name from best.txt.

  Args:
      run_dir: Training run directory containing best.txt.

  Returns:
      Model name string, or None if file missing or unparseable.
  """
  best_file = run_dir / "best.txt"
  if not best_file.exists():
    logger.warning("best.txt not found in %s — cannot promote", run_dir)
    return None

  with open(best_file) as f:
    for line in f:
      if line.startswith("Best Model:"):
        return line.replace("Best Model:", "").strip()

  logger.warning("Could not parse best model name from %s", best_file)
  return None


def _register_model(
  model: object,
  best_model_name: str,
  run_id: str,
  candidate_metrics: dict[str, float],
) -> bool:
  """Register the model in the MLflow Model Registry.

  Args:
      model:            Fitted sklearn estimator to register.
      best_model_name:  Name of the best model (used as run tag).
      run_id:           Training run identifier (used as run tag).
      candidate_metrics: Candidate eval metrics stored on promotion run.

  Returns:
      True if registration succeeded, False otherwise.
  """
  try:
    with mlflow.start_run(run_name=f"promote_{best_model_name}_{run_id}"):
      mlflow.set_tag("promotion", "true")
      mlflow.set_tag("run_id", run_id)
      mlflow.set_tag("promoted_model", best_model_name)
      mlflow.sklearn.log_model(
        model,
        artifact_path="model",
        registered_model_name=_REGISTERED_MODEL_NAME,
      )
      if candidate_metrics:
        eval_metrics = {f"eval_{k}": float(v) for k, v in candidate_metrics.items()}
        mlflow.log_metrics(eval_metrics)
  except Exception:
    logger.exception("Model registration failed for %s", best_model_name)
    return False
  return True


def _transition_to_production(client: MlflowClient, new_version: str) -> bool:
  """Archive old Production versions and promote new_version to Production.

  Args:
      client:       MLflow tracking client.
      new_version:  Version string to promote.

  Returns:
      True if transition succeeded, False otherwise.
  """
  previous_prod_versions: list[str] = []
  try:
    all_versions = client.search_model_versions(f"name='{_REGISTERED_MODEL_NAME}'")
    for mv in all_versions:
      if mv.current_stage == "Production" and mv.version != new_version:
        previous_prod_versions.append(mv.version)

    client.transition_model_version_stage(
      name=_REGISTERED_MODEL_NAME,
      version=new_version,
      stage="Production",
    )
    logger.info(
      "Promoted '%s' version %s to Production",
      _REGISTERED_MODEL_NAME,
      new_version,
    )

    # Archive old production versions only after new version is safely promoted.
    for old_version in previous_prod_versions:
      client.transition_model_version_stage(
        name=_REGISTERED_MODEL_NAME,
        version=old_version,
        stage="Archived",
      )
      logger.info(
        "Archived previous Production version %s of '%s'",
        old_version,
        _REGISTERED_MODEL_NAME,
      )
  except Exception:
    logger.exception(
      "Stage transition failed for version %s of '%s'",
      new_version,
      _REGISTERED_MODEL_NAME,
    )
    return False
  return True


def _load_and_register(
  run_dir: Path,
  best_model_name: str,
  run_id: str,
  candidate_metrics: dict[str, float],
) -> bool:
  """Load the best model pickle and register it in the MLflow Model Registry.

  Checks that the pickle exists, loads the fitted estimator from the
  GridSearchCV result, then delegates to _register_model. Returns False on
  any failure so the caller can treat it as a single boolean gate.

  Args:
      run_dir:          Training run directory containing the pickle file.
      best_model_name:  Model name used to locate ``{model}.pkl``.
      run_id:           Training run identifier (logged as an MLflow tag).
      candidate_metrics: Candidate eval metrics logged during registration.

  Returns:
      True if loading and registration both succeeded, False otherwise.
  """
  pkl_path = run_dir / f"{best_model_name}.pkl"
  if not pkl_path.exists():
    logger.warning("Model pickle not found at %s — cannot promote", pkl_path)
    return False
  try:
    grid = joblib.load(pkl_path)
    model = grid.best_estimator_
  except Exception:
    logger.exception("Could not load model from %s", pkl_path)
    return False
  return _register_model(model, best_model_name, run_id, candidate_metrics)


def _read_candidate_metrics(run_dir: Path, best_model_name: str) -> dict[str, float]:
  """Read candidate eval metrics from eval_{model}.json.

  Args:
      run_dir: Training run directory.
      best_model_name: Best model identifier.

  Returns:
      Metrics dictionary or empty dict when file is missing.
  """
  eval_path = run_dir / f"eval_{best_model_name}.json"
  if not eval_path.exists():
    logger.warning("Eval file not found at %s", eval_path)
    return {}
  try:
    with open(eval_path) as f:
      raw = json.load(f)
  except Exception:
    logger.exception("Could not parse eval metrics at %s", eval_path)
    return {}

  return {k: float(v) for k, v in raw.items() if isinstance(v, int | float)}


def _load_baseline_metrics(
  client: MlflowClient,
) -> tuple[str | None, dict[str, float] | None]:
  """Load production baseline version and metrics from MLflow.

  Args:
      client: MLflow tracking client.

  Returns:
      Tuple of (version, metrics) where metrics can be None.
  """
  try:
    versions = client.get_latest_versions(_REGISTERED_MODEL_NAME, stages=["Production"])
  except Exception:
    logger.warning("Could not retrieve production baseline from registry")
    return None, None

  if not versions:
    return None, None

  version = versions[0]
  try:
    run_data = client.get_run(version.run_id).data
  except Exception:
    logger.warning("Could not load run data for production version %s", version.version)
    return version.version, None

  metrics: dict[str, float] = {}
  for key in ("eval_mae", "eval_rmse", "eval_r2", "mae", "rmse", "r2"):
    if key in run_data.metrics:
      metrics[key.replace("eval_", "")] = float(run_data.metrics[key])

  return version.version, metrics or None


def _get_new_version(client: MlflowClient, best_model_name: str) -> str | None:
  """Return the version string of the model just registered in stage None.

  Queries the Model Registry for the newest version in the ``"None"`` stage
  (i.e. the version created by the preceding _load_and_register call) and
  returns its version string, or None if the query fails or returns empty.

  Args:
      client:           MLflow tracking client.
      best_model_name:  Model name, used only for log messages.

  Returns:
      Version string, or None if the fetch failed or returned no versions.
  """
  try:
    versions = client.get_latest_versions(_REGISTERED_MODEL_NAME, stages=["None"])
    if not versions:
      logger.warning(
        "No new version found in registry for '%s'", _REGISTERED_MODEL_NAME
      )
      return None
    new_version = versions[0].version
  except Exception:
    logger.exception("Could not fetch latest version of '%s'", _REGISTERED_MODEL_NAME)
    return None
  else:
    logger.info(
      "Registered %s as version %s of '%s'",
      best_model_name,
      new_version,
      _REGISTERED_MODEL_NAME,
    )
    return new_version


def promote_best_model(run_id: str) -> str | None:
  """Register and promote the best model from a training run to Production.

  Reads best.txt to identify the best model, loads its pickle, registers
  it in the MLflow Model Registry as a new version of _REGISTERED_MODEL_NAME,
  archives any existing Production version, and transitions the new version
  to the "Production" stage.

  Requires a non-filesystem tracking URI to use the Model Registry.
  Set MLFLOW_TRACKING_URI to a database-backed URI (e.g. sqlite:///mlflow.db)
  when calling this function.

  Args:
      run_id: Training run identifier (subdirectory under models_root).

  Returns:
      The new model version string, or None if promotion failed.
  """
  promoted_version: str | None = None

  if TRAIN_USE_DUMMY_DATA:
    logger.info("TRAIN_USE_DUMMY_DATA=True — skipping model promotion")
  else:
    run_dir = Paths.models_root / run_id
    best_model_name = _read_best_model_name(run_dir)
    if best_model_name:
      candidate_metrics = _read_candidate_metrics(run_dir, best_model_name)

      _setup_experiment()
      client = MlflowClient()

      _, baseline_metrics = _load_baseline_metrics(client)
      guard_config = load_gate_config()
      guard_result = evaluate_regression_guardrail(
        candidate_metrics,
        baseline_metrics,
        guard_config.max_regression_degradation,
      )
      if not guard_result["passed"]:
        logger.error(
          "Regression guardrail failed for run %s: %s",
          run_id,
          guard_result.get("fail_reasons", []),
        )
      else:
        loaded = _load_and_register(run_dir, best_model_name, run_id, candidate_metrics)
        if loaded:
          new_version = _get_new_version(client, best_model_name)
          if new_version is not None and _transition_to_production(client, new_version):
            promoted_version = new_version

  return promoted_version


if __name__ == "__main__":
  import argparse

  parser = argparse.ArgumentParser(
    description="Log training run to MLflow and optionally promote best model."
  )
  parser.add_argument("--runid", "-r", required=True, help="Training run ID")
  parser.add_argument(
    "--promote",
    action="store_true",
    help="Promote best model to Production after logging",
  )
  args = parser.parse_args()

  log_run_to_mlflow(args.runid)
  if args.promote:
    promote_best_model(args.runid)
