# Training Module

ML training pipeline for ticket time prediction. Includes ETL (GitHub issue ingestion, feature engineering), model training (Random Forest, Linear, SVM, XGBoost), and bias detection/mitigation.

## Setup

**Required environment variables:**

```sh
GITHUB_TOKEN=ghp_...                 # GitHub Personal Access Token (classic)
GMAIL_APP_USERNAME=your@email.com    # Gmail SMTP username
GMAIL_APP_PASSWORD=...               # Gmail app password (see https://support.google.com/accounts/answer/185833)
```

Add these to `.env` at the repo root.

## Quick Start

```bash
# Run the full training pipeline
just train

# Train specific models only
just train -m forest linear

# Run tests
just pytest apps/training

# Lint and type-check (before committing)
just pylint apps/training
```

## Structure

```
training/
├── analysis/          # Standalone analysis scripts for data exploration
├── bias/              # Bias detection and mitigation
│   ├── analyzer.py    # BiasAnalyzer - compares performance across slices
│   ├── mitigation.py  # BiasMitigator - resampling and sample weights
│   ├── report.py      # BiasReport - generates formatted reports
│   └── slicer.py      # DataSlicer - splits data into subgroups
├── cmd/               # CLI entry points
│   └── train.py       # Main training orchestrator
├── etl/               # Extract, Transform, Load pipeline
│   ├── ingest/        # GitHub API scraping, CSV conversion, resume extraction
│   │   ├── scrape_github_issues_graphql.py  # Active GraphQL scraper
│   │   ├── scrape_github_issues.py          # Legacy REST scraper (deprecated)
│   │   ├── transform.py                      # Feature engineering pipeline
│   │   └── coldstart.py                      # Stub profile generation
│   └── postload/      # Post-ingestion processing
│       └── replay.py  # Ticket replay for profile history (Experience Decay)
└── trainers/          # ML model training implementations
    ├── train_forest.py    # Random Forest regressor
    ├── train_linear.py    # Linear Regression baseline
    ├── train_svm.py       # SVM with kernel approximation
    ├── train_xgboost.py   # XGBoost gradient boosting
    └── utils/             # Shared training utilities and harness
```

## ETL Pipeline

**Purpose:** Ingest GitHub issues from Ansible, Terraform, and Prometheus repos. Generate embeddings, extract keywords, detect anomalies, and mitigate bias.

**Run via Airflow:** The `ticket_etl` DAG orchestrates the full pipeline. See `dags/ticket_etl.py` and [docker/README.md](../../docker/README.md) for detailed DAG documentation.

### Pipeline Steps (ticket_etl DAG)

1. **Validate Config** (`validate_config`) — Parses runtime parameters (e.g., `limit_per_state`), creates timestamped output directory at `data/github_issues-<timestamp>/`.

2. **Scrape GitHub Issues** (`scrape_github_issues`) — Uses GraphQL API to fetch issues from 3 repos (Ansible, Terraform, Prometheus) across 3 states (closed, open+assigned, open+unassigned). Saves to `tickets_raw.json.gz`. Rate-limited by GitHub API.

3. **Transform** (`transform_tickets`) — Feature engineering: generates 384-dim embeddings via `ml_core.embeddings`, extracts skill keywords via `ml_core.keywords`, parses labels and metadata. Saves to `tickets_transformed_improved.jsonl.gz`.

4. **Anomaly Detection** (`detect_anomalies`) — Statistical checks for missing values, outliers (z-score method), and schema violations using `ml_core.anomaly.AnomalyDetector` and `SchemaValidator`. Fails pipeline if >30 anomalies detected. Saves `anomaly_report.txt`.

5. **Bias Detection** (`detect_bias`) — **Runs in parallel with Step 6.** Analyzes assignment patterns across demographic groups (repo, seniority) using `training.bias.BiasAnalyzer` with Fairlearn's `MetricFrame`.

6. **Bias Mitigation** (`mitigate_bias`) — **Runs in parallel with Step 5.** Calculates inverse-frequency sample weights using `training.bias.BiasMitigator` to balance underrepresented groups. Saves `sample_weights.json`.

7. **Prepare Bias Report** (`prepare_bias_report`) — Waits for Steps 5 & 6, combines results into human-readable `bias_report.txt` with per-slice performance metrics and mitigation recommendations.

8. **Save Artifacts** (`save_artifacts`) — Persists all compressed datasets (`.gz`), weights (`.json`), and text reports (`.txt`) to the timestamped output directory.

9. **Load to Database** (`load_to_db`) — Upserts tickets and assignments into Postgres. Uses `training.etl.ingest.coldstart` to create stub profiles in `users` table for any new engineers (no resume yet). Vectors stored with pgvector extension.

10. **Replay Closed Tickets** (`replay_tickets`) — Applies Experience Decay formula to engineer profiles for completed assignments using `training.etl.postload.replay`. Updates `profile_vector` in `users` table: `profile_vector ← α · profile_vector + (1 − α) · ticket_vector` (default α = 0.95).

11. **Send Email** (`send_email`) — Sends Gmail notification to `mlopsgroup29@gmail.com` with anomaly and bias reports attached. Runs on both success and failure.

**Outputs:**
- `data/github_issues-<timestamp>/tickets_transformed_improved.jsonl.gz` — Feature-engineered training data
- `data/github_issues-<timestamp>/sample_weights.json` — Bias mitigation weights
- `data/github_issues-<timestamp>/anomaly_report.txt` — Data quality report
- `data/github_issues-<timestamp>/bias_report.txt` — Fairness analysis

**Direct execution (for testing):**

> [!IMPORTANT]
> Consider direct execution as deprecated!


```bash
# Scrape GitHub issues using GraphQL API (active scraper)
uv run -m training.etl.ingest.scrape_github_issues_graphql

# Transform raw data to feature-engineered format
uv run -m training.etl.ingest.transform
```

**GitHub Scrapers:**
- `scrape_github_issues_graphql.py` — **Active production scraper** (GraphQL, fast, comprehensive)
- `scrape_github_issues_sample.py` — demo scraper which balances between all 3 issue types and scrapes limited subset (faster)

**Scraper outputs:** `data/github_issues/all_tickets.json` (contains all 3 issue types: closed, open+assigned, open+unassigned)

## Model Training

**Supported models:** Random Forest, Linear Regression, SVM (kernel approximation), XGBoost.

> [!IMPORTANT]
> Current trainers use dummy/sample data for validation and are not trained on the full dataset. Full model training on production data is planned for the next deliverable. The training harness, hyperparameter search, and evaluation pipeline are production-ready and validated with subset data (`Dataset.as_sklearn_cv_split(subset_size=20)`).

> [!IMPORTANT]
> Model training uses the bias mitigation information output by the training pipeline to better train the model and evaluate the performance by repository!


**Training outputs** (saved to `models/{run_id}/`):
- `{model_name}.pkl` — Trained model artifact
- `eval_{model_name}.json` — Metrics (MAE, MSE, RMSE, R²)
- `bias_{model_name}_{feature}.txt` — Per-feature bias report (repo, seniority)
- `best.txt` — Name of best-performing model

**Performance:** Example results from validation run available in [assets/performance.png](./assets/performance.png).

### Adding a New Model

1. Create `training/trainers/train_mymodel.py` implementing `fit_grid(x, y, cv_split)` and `main(run_id)`.
2. Register in `training/cmd/train.py`: add `"mymodel"` to the `models` set.
3. Add tests to `tests/test_trainers.py` with `@pytest.mark.filterwarnings("ignore")`.
4. Test with subset data: `Dataset.as_sklearn_cv_split(subset_size=20)`.

## Bias Detection and Mitigation

**Components:**
- **DataSlicer** — Slices data by repo, seniority, labels, completion time.
- **BiasAnalyzer** — Compares model performance across slices using Fairlearn's `MetricFrame`. Flags groups exceeding relative gap threshold.
- **BiasMitigator** — Resampling, inverse-frequency sample weighting, prediction adjustment (mean/variance equalisation), Fairlearn constrained training.
- **BiasReport** — Generates human-readable fairness reports.

**Usage:**
```python
from training.bias import DataSlicer, BiasAnalyzer, BiasMitigator

slicer = DataSlicer(data)
slices = slicer.slice_by_repo()

analyzer = BiasAnalyzer(threshold=0.1)
result = analyzer.compare_slices(slices, "y_true", "y_pred")

weights = BiasMitigator.compute_sample_weights(data, "repo")
```

**Mitigation strategy:** Sample weighting (inverse-frequency) is applied during training to balance underrepresented groups. Preferred over resampling to avoid overfitting duplicated patterns. Requires sklearn models supporting per-sample weights.
