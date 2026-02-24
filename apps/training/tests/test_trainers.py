"""Tests for training models using different trainers."""

import pytest
from sklearn.model_selection import RandomizedSearchCV
from training.dataset import Dataset
from training.trainers.train_forest import fit_grid as fit_grid_forest
from training.trainers.train_linear import fit_grid as fit_grid_linear
from training.trainers.train_svm import fit_grid_approx as fit_grid_svm
from training.trainers.train_xgboost import fit_grid as fit_grid_xgboost


class TestForestTrainer:
  """Tests for Random Forest trainer."""

  @pytest.mark.filterwarnings("ignore")
  def test_forest_trainer_fits_successfully(self) -> None:
    """Test that forest trainer can fit on small dataset."""
    x_combined, y_combined, cv_split = Dataset.as_sklearn_cv_split(subset_size=20)

    grid = fit_grid_forest(x_combined, y_combined, cv_split)

    assert isinstance(grid, RandomizedSearchCV)
    assert grid.best_estimator_ is not None
    assert hasattr(grid, "cv_results_")

  @pytest.mark.filterwarnings("ignore")
  def test_forest_trainer_predictions(self) -> None:
    """Test that forest trainer can make predictions."""
    x_combined, y_combined, cv_split = Dataset.as_sklearn_cv_split(subset_size=20)

    grid = fit_grid_forest(x_combined, y_combined, cv_split)
    test_dataset = Dataset(split="test", subset_size=20)
    x_test = test_dataset.load_x()
    predictions = grid.predict(x_test)

    assert predictions.shape[0] == 20


class TestLinearTrainer:
  """Tests for Linear trainer."""

  @pytest.mark.filterwarnings("ignore")
  def test_linear_trainer_fits_successfully(self) -> None:
    """Test that linear trainer can fit on small dataset."""
    x_combined, y_combined, cv_split = Dataset.as_sklearn_cv_split(subset_size=20)

    grid = fit_grid_linear(x_combined, y_combined, cv_split)

    assert isinstance(grid, RandomizedSearchCV)
    assert grid.best_estimator_ is not None
    assert hasattr(grid, "cv_results_")

  @pytest.mark.filterwarnings("ignore")
  def test_linear_trainer_predictions(self) -> None:
    """Test that linear trainer can make predictions."""
    x_combined, y_combined, cv_split = Dataset.as_sklearn_cv_split(subset_size=20)

    grid = fit_grid_linear(x_combined, y_combined, cv_split)
    test_dataset = Dataset(split="test", subset_size=20)
    x_test = test_dataset.load_x()
    predictions = grid.predict(x_test)

    assert predictions.shape[0] == 20


class TestSVMTrainer:
  """Tests for SVM trainer with kernel approximation."""

  @pytest.mark.filterwarnings("ignore")
  def test_svm_trainer_fits_successfully(self) -> None:
    """Test that SVM trainer can fit on small dataset."""
    x_combined, y_combined, cv_split = Dataset.as_sklearn_cv_split(subset_size=20)

    grid = fit_grid_svm(x_combined, y_combined, cv_split)

    assert isinstance(grid, RandomizedSearchCV)
    assert grid.best_estimator_ is not None
    assert hasattr(grid, "cv_results_")

  @pytest.mark.filterwarnings("ignore")
  def test_svm_trainer_predictions(self) -> None:
    """Test that SVM trainer can make predictions."""
    x_combined, y_combined, cv_split = Dataset.as_sklearn_cv_split(subset_size=20)

    grid = fit_grid_svm(x_combined, y_combined, cv_split)
    test_dataset = Dataset(split="test", subset_size=20)
    x_test = test_dataset.load_x()
    predictions = grid.predict(x_test)

    assert predictions.shape[0] == 20


class TestXGBoostTrainer:
  """Tests for XGBoost trainer."""

  @pytest.mark.timeout(120)
  @pytest.mark.filterwarnings("ignore")
  def test_xgboost_trainer_fits_successfully(self) -> None:
    """Test that XGBoost trainer can fit on small dataset."""
    x_combined, y_combined, cv_split = Dataset.as_sklearn_cv_split(subset_size=20)

    grid = fit_grid_xgboost(x_combined, y_combined, cv_split)

    assert isinstance(grid, RandomizedSearchCV)
    assert grid.best_estimator_ is not None
    assert hasattr(grid, "cv_results_")

  @pytest.mark.timeout(120)
  @pytest.mark.filterwarnings("ignore")
  def test_xgboost_trainer_predictions(self) -> None:
    """Test that XGBoost trainer can make predictions."""
    x_combined, y_combined, cv_split = Dataset.as_sklearn_cv_split(subset_size=20)

    grid = fit_grid_xgboost(x_combined, y_combined, cv_split)
    test_dataset = Dataset(split="test", subset_size=20)
    x_test = test_dataset.load_x()
    predictions = grid.predict(x_test)

    assert predictions.shape[0] == 20
