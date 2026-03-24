# %%

# uncomment when running in notebook mode
# import sys
# sys.path.append("..")

from scipy.stats import loguniform
from shared.configuration import RANDOM_SEED
from sklearn.linear_model import SGDRegressor
from sklearn.model_selection import PredefinedSplit, RandomizedSearchCV
from training.trainers.utils.harness import X_t, Y_t, load_fit_dump


# %%
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
    n_grams: the number of n-grams to fit

  Returns:
      result of the grid search.
  """
  param_grid = [
    {
      "loss": ["squared_error", "huber", "epsilon_insensitive"],
      "penalty": ["l2", "l1", "elasticnet"],
      "alpha": loguniform(1e-5, 1e5),
    }
  ]
  model = SGDRegressor(random_state=RANDOM_SEED, max_iter=4000)
  grid = RandomizedSearchCV(
    estimator=model,
    param_distributions=param_grid,
    cv=cv_split,
    scoring="neg_mean_squared_error",
    refit=True,
    n_jobs=-1,
    n_iter=20,
    random_state=RANDOM_SEED,
    error_score="raise",  # type: ignore
    verbose=2,
  )

  return grid.fit(x, y, sample_weight=sample_weight)


def main(run_id: str) -> None:
  """Trains linear models on all the feature datasets."""
  load_fit_dump(fit_grid, run_id, "linear")


if __name__ == "__main__":
  main("TESTING")
# %%
