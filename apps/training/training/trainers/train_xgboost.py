import xgboost as xgb
from shared.configuration import RANDOM_SEED
from sklearn.model_selection import PredefinedSplit, RandomizedSearchCV
from training.trainers.utils.harness import X_t, Y_t, load_fit_dump

# %%

XGB_VERBOSE = 1  # 3=debug, 2=info, 1=warning
xgb.set_config(verbosity=XGB_VERBOSE)


def fit_grid(
  x: X_t,
  y: Y_t,
  cv_split: PredefinedSplit,
  sample_weight: Y_t | None = None,
) -> RandomizedSearchCV:
  """Performs grid search and then returns the result!

  Args:
    x: x data to use for training
    y: true labels of dataset
    cv_split: the predefined split to use
    sample_weight: per-sample weights for bias-aware training, or None
    n_grams: the number of ngrams to fit

  Returns:
      result of the grid search.
  """
  # Grid params and usage of model inspired by following references:
  #   https://github.com/szilard/benchm-ml?tab=readme-ov-file#boosting-gradient-boosted-treesgradient-boosting-machines
  #   https://xgboost.readthedocs.io/en/stable/parameter.html
  # defaults are max_depth=6, learning_rate=.3, min_child_weight=1, n_estimators=100
  #   gamma=0, subsample=1, colsample_bytree=1
  param_grid = [
    {
      "max_depth": [1, 3, 4, 5, 6, 7],
      "learning_rate": [
        0.01,
        0.03,
        0.1,
        0.3,
        0.5,
      ],
      "min_child_weight": [1, 5, 10],
      "n_estimators": [10, 30, 50],
      "gamma": [0, 0.1, 1],
      "subsample": [0.1, 0.2, 0.3],
      "colsample_bytree": [0.2, 0.3, 0.4],
    }
  ]

  model = xgb.XGBRegressor(
    random_state=RANDOM_SEED,
    device="cpu",
    tree_method="hist",
    max_bin=63,
    n_jobs=-1,
  )
  grid = RandomizedSearchCV(
    estimator=model,
    param_distributions=param_grid,
    cv=cv_split,
    scoring="neg_mean_squared_error",
    refit=True,
    n_jobs=1,
    n_iter=20,
    random_state=RANDOM_SEED,
    error_score="raise",  # type: ignore
    verbose=2,
  )

  return grid.fit(x, y, sample_weight=sample_weight)


def main(run_id: str) -> None:
  """Trains xgboost models on all the feature datasets."""
  load_fit_dump(fit_grid, run_id, "xgboost")


if __name__ == "__main__":
  main("TESTING")

# %%
