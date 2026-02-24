# Training Module

ML model training pipeline for ticket time prediction using multiple regression algorithms.

This includes ETL and model training.

```
training
├── analysis                # standalone analysis scripts
├── bias                    # bias detection and mitigation
│   ├── analyzer.py
│   ├── mitigation.py
│   ├── report.py
│   └── slicer.py
├── cmd                     # scripts to run
├── dataset.py              # Dataset class
├── etl
│   └── ingest              # "Extract" part of ETL
└── trainers                # ML model trainers
    ├── train_forest.py
    ├── train_linear.py
    ├── train_svm.py
    ├── train_xgboost.py
    └── utils
```
## Setup

To use this module, you must:
- create a gmail app (Follow the instruction provided here [link](https://support.google.com/accounts/answer/185833) and get your smtp password)
- create github authentication token: You want to go to developer settings and then create a "GitHub Personal Access Token (classic)" (see [link](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens))

Then you must add the following fields to your `.env` file

```sh
GMAIL_APP_USERNAME=YOUR_EMAIL
GMAIL_APP_PASSWORD=...
GITHUB_TOKEN=...
```

## ETL Submodule

### Ingress

#### GitHub Issue Ingestion

This module ingests closed GitHub issues with assignees and produces
a compressed JSON dataset for downstream processing.

##### Setup
- Create a GitHub Personal Access Token (classic)
- Add it to a .env file as GITHUB_TOKEN

##### Run
```sh
uv run -m training.etl.ingest.scrape_github_issues
uv run -m training.etl.ingest.csv_to_json
```
##### Outputs
- data/github_issues/tickets_raw.csv
- data/github_issues/tickets_final.json.gz

## Trainers Submodule

This module trains and evaluates various machine learning models to predict ticket resolution times. It currently supports:

- **Random Forest** - Ensemble method for robust predictions
- **Linear Regression** - Fast, interpretable baseline
- **SVM (with kernel approximation)** - Non-linear modeling with scalability
- **XGBoost** - Gradient boosting for high performance

After each training run, the harness automatically runs bias evaluation (via `evaluate_bias`) across `repo` and `seniority` sensitive features and saves a per-feature bias report alongside the eval metrics.

### Quick Start

#### Run Training

```bash
# Validates the training pipeline
just pytest .

# Train specific models (from repo root)
just train -m forest linear

# Train with custom run ID
just train -r my_run_123
```

#### Output

Training outputs are saved to `models/{run_id}/`:

- `{model_name}.pkl` - Trained model file
- `eval_{model_name}.json` - Performance metrics (MAE, MSE, RMSE, R²)
- `bias_{model_name}_{feature}.txt` - Bias report per sensitive feature (e.g. `bias_forest_repo.txt`)
- `best.txt` - contains name of the best performing model

#### Performance Visualization

Example metrics from recent training run:

![Performance Results](./assets/performance.png)


### Adding New Models

To add a new model:

1. **Create trainer module** - `apps/training/training/trainers/train_mymodel.py`
   ```python
   from training.trainers.utils.harness import X_t, Y_t, load_fit_dump
   from sklearn.model_selection import PredefinedSplit, RandomizedSearchCV

   def fit_grid(x: X_t, y: Y_t, cv_split: PredefinedSplit) -> RandomizedSearchCV:
       """Implement hyperparameter grid search."""
       # Your implementation
       return grid.fit(x, y)

   def main(run_id: str) -> None:
       load_fit_dump(fit_grid, run_id, "mymodel")

   if __name__ == "__main__":
       main("TESTING")
   ```

2. **Register model** - Update `models` set in `training/cmd/train.py`:
   ```python
   models = {"forest", "linear", "svm", "xgboost", "mymodel"}
   ```

3. **Add tests** - Extend `tests/test_trainers.py` with trainer tests using `@pytest.mark.filterwarnings("ignore")` decorator

4. **Test with subset data**:
   ```python
   from training.dataset import Dataset
   x, y, cv_split = Dataset.as_sklearn_cv_split(subset_size=20)
   ```

## Bias Detection and Mitigation

The `training.bias` module provides tools for detecting and mitigating bias in model predictions. Bias detection ensures the ticket assignment model performs fairly across subgroups such as repositories, seniority levels, and ticket types.

### Components

- **`DataSlicer` (`slicer.py`)** — Splits data into subgroups for analysis. Supports slicing by repository, seniority level, labels, completion time buckets, and technical keywords.
- **`BiasAnalyzer` (`analyzer.py`)** — Detects bias by comparing model performance across slices using Fairlearn's `MetricFrame`. Supports both regressor (MAE/RMSE/R²) and recommendation (NDCG/MRR) metric sets, and flags groups exceeding a configurable relative gap threshold.
- **`BiasMitigator` (`mitigation.py`)** — Provides resampling to balance underrepresented groups, inverse-frequency sample weights for fair training, prediction adjustment (mean equalisation and variance scaling), and Fairlearn `ExponentiatedGradient` constrained training.
- **`BiasReport` (`report.py`)** — Generates formatted text reports summarising which dimensions show bias and the per-slice performance metrics.

### Bias Analysis Results

Analysis of 61,271 tickets revealed the following distribution imbalances:

| Dimension | Group | Count |
|---|---|---|
| Repository | Ansible | 33,286 |
| Repository | Terraform | 21,611 |
| Repository | Prometheus | 6,374 |
| Completion time | Slow (>24 h) | 36,088 |
| Completion time | Fast (<5 h) | 14,457 |
| Completion time | Medium | 7,874 |
| Completion time | Unknown | 2,852 |

Repository imbalance is ~5× between the largest and smallest group. All tickets are currently mapped to mid seniority — the seniority mapping logic needs improvement.

### Mitigation Applied

**Resampling** duplicates Terraform and Prometheus tickets to match Ansible (33,286 each), yielding a balanced dataset of 99,858 tickets.

**Sample weighting** assigns inverse-frequency weights so underrepresented groups receive higher importance during training:

| Repo | Weight |
|---|---|
| Prometheus | 3.2042 |
| Terraform | 0.9451 |
| Ansible | 0.6136 |

**Conclusion**

Resampling increases dataset size without adding new information and may overfit to duplicated patterns. Sample weighting preserves original data but requires the training algorithm to support per-sample weights. Both approaches prioritise fairness while accepting a potential minor reduction in overall performance. Because we use sklearn, we
are only training models which enable us to use sample weighting.

### Usage

```python
from training.bias import DataSlicer, BiasAnalyzer, BiasMitigator, BiasReport

# Slice data
slicer = DataSlicer(data)
slices = slicer.slice_by_repo()

# Detect bias
analyzer = BiasAnalyzer(threshold=0.1)
result = analyzer.compare_slices(slices, "y_true", "y_pred")

# Mitigate
balanced_data = BiasMitigator.resample_underrepresented(data, "repo")
weights = BiasMitigator.compute_sample_weights(data, "repo")

# Report
report = BiasReport.generate_text_report(analysis)
BiasReport.save_report(analysis, "bias_report.txt")
```

### Standalone Analysis Script

```bash
uv run python -m training.analysis.detect_bias
```

This script loads `data/github_issues/tickets_transformed_improved.jsonl` and prints a data-distribution breakdown by repository, seniority, completion-time bucket, and label.

## Testing

```bash
# Run all training tests with warning suppression
just pytest apps/training/tests/

# Run with verbose output
just pytest apps/training/tests/ -v
```
