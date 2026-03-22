from typing import Callable

import numpy as np
import pandas as pd
import polars as pl
from shared import get_logger
from shared.cache import JsonSaver, fs_cache
from shared.configuration import Paths
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import PredefinedSplit, RandomizedSearchCV
from training.bias import BiasAnalyzer, BiasReport
from training.dataset import Dataset, X_t, Y_t

logger = get_logger(__name__)

# Default sensitive features to check for bias
DEFAULT_SENSITIVE_FEATURES = ["repo", "seniority"]


def load_fit_dump(
  fit_grid: Callable[
    [X_t, Y_t, PredefinedSplit, Y_t | None],
    RandomizedSearchCV,
  ],
  run_id: str,
  model_name: str,
) -> None:
  """Fits model by loading the appropriate dataset, doing cv, saving model,
  and saving eval metrics.

  Args:
      fit_grid: function to do hyperparam search, now accepting n_gram as well
      run_id: UUID of the training run
      model_name: identified of the type of model (i.e. logistic)
  """

  # Define the cached fit function
  @fs_cache(Paths.models_root / run_id / f"{model_name}.pkl")
  def _run_search() -> RandomizedSearchCV:
    # 1. Get the combined data, PredefinedSplit, and per-sample weights
    x_comp, y_comp, cv_split, weights = Dataset.as_sklearn_cv_split_with_weights()

    # 2. Pass them into the fit_grid logic
    return fit_grid(x_comp, y_comp, cv_split, weights)

  # Execute (either loads from disk or runs the fit)
  res = _run_search()

  # Display results and evaluate on test set
  pretty_print_gridsearch(res, run_id, model_name)


def save_cv_results(
  grid: RandomizedSearchCV,
  run_id: str,
  model_name: str,
) -> None:
  """Save GridSearch cv_results_ to JSON for later sensitivity analysis.

  Args:
      grid:       Fitted RandomizedSearchCV object.
      run_id:     UUID of the training run.
      model_name: Identifier of the model type.
  """
  cv_path = Paths.models_root / run_id / f"cv_results_{model_name}.json"
  if cv_path.exists():
    logger.info("cv_results already saved at %s", cv_path)
    return

  # cv_results_ contains numpy types — convert to plain Python for JSON
  serializable: dict[str, list] = {}
  for key, val in grid.cv_results_.items():
    if hasattr(val, "tolist"):
      serializable[key] = val.tolist()
    else:
      serializable[key] = list(val)

  with open(cv_path, "w") as f:
    import json as _json

    _json.dump(serializable, f)
  logger.info("cv_results saved to %s", cv_path)


def get_test_accuracy(
  grid: RandomizedSearchCV,
  run_id: str,
  model_name: str,
) -> None:
  """Computes the test accuracy for the best model in the grid search.

  Args:
      grid: the sklearn hyperparam grid
      run_id: UUID of the training run
      model_name: identified of the type of model (i.e. logistic)
  """

  @fs_cache(Paths.models_root / run_id / f"eval_{model_name}.json", saver=JsonSaver())
  def compute_metrics() -> dict[str, float]:
    test_dataset = Dataset(split="test")

    x = test_dataset.load_x()  # noqa: N806
    y = test_dataset.load_y()

    y_pred = grid.predict(x)
    mse = mean_squared_error(y, y_pred)

    return {
      "mae": mean_absolute_error(y, y_pred),
      "mse": mse,
      "rmse": np.sqrt(mse),
      "r2": r2_score(y, y_pred),
    }

  metrics = compute_metrics()

  logger.info("Test metrics: %s", metrics)


def evaluate_bias(
  grid: RandomizedSearchCV,
  run_id: str,
  model_name: str,
  sensitive_feature: str = "repo",
) -> dict | None:
  """Run bias analysis on model predictions.

  Evaluates the model on slices of the test set defined by sensitive_feature
  and saves a bias report. Bias detection uses Fairlearn MetricFrame to
  compute metrics per subgroup. Sample weighting applied during training
  is the primary mitigation strategy.

  Args:
      grid: Fitted grid search with best model
      run_id: UUID of the training run
      model_name: Identifier of the model type
      sensitive_feature: Feature to use for bias analysis (e.g. "repo", "seniority")

  Returns:
      Bias analysis results, or None if sensitive feature not available
  """
  model_type = "regressor"
  threshold = 0.4
  test_dataset = Dataset(split="test")

  x = test_dataset.load_x()
  y = test_dataset.load_y()
  y_pred = grid.predict(x)

  # Try to get sensitive features from test data metadata
  try:
    test_meta = test_dataset.load_metadata()
    if sensitive_feature not in test_meta.columns:
      logger.warning(
        "Bias analysis skipped: %r not in test metadata", sensitive_feature
      )
      return None
    sensitive_features = pd.Series(test_meta[sensitive_feature].to_numpy())
  except (AttributeError, FileNotFoundError):
    logger.warning("Bias analysis skipped: metadata not available")
    return None

  analyzer = BiasAnalyzer(threshold=threshold, model_type=model_type)
  y_true_series = pd.Series(y)
  y_pred_series = pd.Series(y_pred)

  analysis = analyzer.detect_bias_fairlearn(
    y_true=y_true_series,
    y_pred=y_pred_series,
    sensitive_features=sensitive_features,
  )

  primary_metric = analysis["primary_metric"]
  logger.info(
    "Bias Analysis (%s): Best=%s (%s=%.4f), Worst=%s (%s=%.4f), Gap=%.1f%%",
    sensitive_feature,
    analysis["best_group"]["name"],
    primary_metric,
    analysis["best_group"][primary_metric],
    analysis["worst_group"]["name"],
    primary_metric,
    analysis["worst_group"][primary_metric],
    analysis["relative_gap"] * 100,
  )

  if analysis["bias_detected"]:
    logger.warning("Bias detected for sensitive feature: %s", sensitive_feature)
  else:
    logger.info("No significant bias detected for: %s", sensitive_feature)

  # Save bias report
  report_path = (
    Paths.models_root / run_id / f"bias_{model_name}_{sensitive_feature}.txt"
  )
  report_data = {
    "summary": {
      "model_type": model_type,
      "total_dimensions_checked": 1,
      "biased_dimensions": [sensitive_feature] if analysis["bias_detected"] else [],
      "bias_count": 1 if analysis["bias_detected"] else 0,
      "overall_bias_detected": analysis["bias_detected"],
    },
    "detailed_results": {sensitive_feature: analysis},
  }
  BiasReport.save_report(report_data, str(report_path))

  return analysis


def pretty_print_gridsearch(
  grid: RandomizedSearchCV,
  run_id: str,
  model_name: str,
) -> None:
  """Given gridsearch cv, creates pretty tabular view.

  Args:
      grid: the gridcv whose results we should display.
      run_id: UUID of the training run
      model_name: identified of the type of model (i.e. logistic)
  """
  df = (
    pl.DataFrame(grid.cv_results_, strict=False)[
      [
        "mean_fit_time",
        "mean_score_time",
        "params",
        "mean_test_score",
        "rank_test_score",
      ]
    ]
    .with_columns(
      pl.col("mean_test_score").round(2),
      *[
        pl.duration(seconds=pl.col(col), time_unit="ms").alias(col)
        for col in ["mean_fit_time", "mean_score_time"]
      ],
      pl.col("params").struct.json_encode(),
    )
    .sort(pl.col("rank_test_score"))
  )
  logger.info("Hyper-parameter search results:")
  with pl.Config(tbl_hide_dataframe_shape=True):
    logger.info("\n%s", df)
    total_time = df["mean_fit_time"].sum() + df["mean_score_time"].sum()
    logger.info("Total training time: %s", total_time)
    get_test_accuracy(grid, run_id, model_name)
    save_cv_results(grid, run_id, model_name)

    # Run bias analysis on test set for all sensitive features
    for feature in DEFAULT_SENSITIVE_FEATURES:
      evaluate_bias(grid, run_id, model_name, sensitive_feature=feature)
