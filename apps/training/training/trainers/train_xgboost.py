import torch
import xgboost as xgb
from shared.configuration import RANDOM_SEED
from sklearn.model_selection import PredefinedSplit, RandomizedSearchCV
from training.dataset import N_CLASSES
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
  param_grid = [
    {
      "max_depth": [3, 4, 5, 6, 7, 8],  # removed 1 (too shallow), added 8
      "learning_rate": [0.01, 0.05, 0.1, 0.3],  # removed 0.5 (too aggressive)
      "min_child_weight": [1, 5, 10],
      "n_estimators": [100, 200, 300],  # was [10, 30, 50] — too few trees
      "gamma": [0, 0.1, 1],
      "subsample": [0.5, 0.7, 0.9],  # was [0.1, 0.2, 0.3] — too low
      "colsample_bytree": [0.5, 0.7, 0.9],  # was [0.2, 0.3, 0.4] — too low
    }
  ]

  model = xgb.XGBClassifier(
    num_class=N_CLASSES,
    objective="multi:softmax",
    random_state=RANDOM_SEED,
    device="gpu" if torch.cuda.is_available() else "cpu",
    tree_method="hist",
    max_bin=63,
    n_jobs=-1,
  )
  grid = RandomizedSearchCV(
    estimator=model,
    param_distributions=param_grid,
    cv=cv_split,
    scoring="f1_macro",
    refit=True,
    n_jobs=1,
    n_iter=30,
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
