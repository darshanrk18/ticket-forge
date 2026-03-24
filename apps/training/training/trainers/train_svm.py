# %%

# uncomment when running in notebook mode
# import sys

# sys.path.append("..")

from scipy.stats import loguniform
from shared.configuration import RANDOM_SEED
from sklearn.kernel_approximation import Nystroem
from sklearn.linear_model import SGDRegressor
from sklearn.model_selection import PredefinedSplit, RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sklearn.svm import SVR
from training.trainers.utils.harness import X_t, Y_t, load_fit_dump


def fit_grid_approx(
  x: X_t,
  y: Y_t,
  cv_split: PredefinedSplit,
  sample_weight: Y_t | None = None,
) -> RandomizedSearchCV:
  """Performs grid search with kernel approximation and then returns the result!

  Args:
    x: x data to use for training
    y: true labels of dataset
    cv_split: the predefined split to use
    sample_weight: per-sample weights (not used; Pipeline routing not implemented)

  Returns:
      result of the grid search.
  """
  param_grid = [
    {
      "kernel__n_components": [250, 500, 1000],
      "kernel__gamma": [10, 1, 0.1, 0.01],
      "kernel__random_state": list(range(1, 1000)),
      "svc__alpha": loguniform(1e-5, 1e5),
    },
  ]
  # don't seed the kernel since we want different features to be extracted
  pipe = Pipeline(
    [
      ("kernel", Nystroem(n_jobs=-1)),
      ("svc", SGDRegressor(random_state=RANDOM_SEED)),
    ]
  )
  grid = RandomizedSearchCV(
    estimator=pipe,
    param_distributions=param_grid,
    cv=cv_split,
    scoring="neg_mean_squared_error",
    refit=True,
    n_iter=1,  # TODO: revert to 50
    random_state=RANDOM_SEED,
    error_score="raise",  # type: ignore
  )

  # sample_weight is not passed: sklearn Pipelines require per-step fit-param
  # routing (set_output API), which adds complexity for minimal gain here.
  return grid.fit(x, y)


def fit_grid_full(
  x: X_t,
  y: Y_t,
  cv_split: PredefinedSplit,
  sample_weight: Y_t | None = None,  # noqa: ARG001 — SVR does not support sample_weight
) -> RandomizedSearchCV:
  """Performs grid search with full SVM (no approximation) and returns result!

  Args:
    x: x data to use for training
    y: true labels of dataset
    cv_split: the predefined split to use
    sample_weight: per-sample weights (not used; SVR does not support sample_weight)

  Returns:
      result of the grid search.
  """
  param_grid = [
    {
      "C": loguniform(1e-3, 1e3),
      "gamma": ["scale", "auto", 0.001, 0.01, 0.1, 1],
      "kernel": ["rbf", "poly", "sigmoid"],
      "epsilon": [0.01, 0.1, 0.2, 0.5],
    },
  ]
  model = SVR()
  grid = RandomizedSearchCV(
    estimator=model,
    param_distributions=param_grid,
    cv=cv_split,
    scoring="neg_mean_squared_error",
    refit=True,
    n_iter=50,
    random_state=RANDOM_SEED,
    error_score="raise",  # type: ignore
    n_jobs=-1,
  )

  # SVR does not support sample_weight in fit(); weights are silently ignored.
  return grid.fit(x, y)


# %%
def main(run_id: str) -> None:
  """Trains svm models on all the feature datasets."""
  # load_fit_dump(fit_grid_approx, run_id, "svm_approx")
  load_fit_dump(fit_grid_full, run_id, "svm_full")


if __name__ == "__main__":
  main("TESTING")
