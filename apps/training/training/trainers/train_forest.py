# %%
# uncomment when running in notebook mode
# import sys
# sys.path.append("..")

from scipy.stats import uniform
from shared.configuration import RANDOM_SEED
from sklearn.ensemble import RandomForestRegressor
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
    n_grams: the number of ngrams being fit

  Returns:
      result of the grid search.
  """
  param_grid = [
    {
      "max_depth": range(5, 30),
      "max_samples": uniform(0.2, 0.6),
      "min_samples_split": range(2, 10),
      "n_estimators": range(10, 100),
    }
  ]
  model = RandomForestRegressor(random_state=RANDOM_SEED, n_jobs=-1)
  grid = RandomizedSearchCV(
    estimator=model,
    param_distributions=param_grid,
    cv=cv_split,
    scoring="neg_mean_squared_error",
    refit=True,
    n_iter=20,
    random_state=RANDOM_SEED,
    error_score="raise",  # type: ignore
    verbose=2,
  )

  return grid.fit(x, y, sample_weight=sample_weight)


def main(run_id: str) -> None:
  """Trains forest models on all the feature datasets."""
  load_fit_dump(fit_grid, run_id, "random_forest")


if __name__ == "__main__":
  main("TESTING")
