# Pipelines Module

Ticket ingestion and ETL workflows for TicketForge. This module owns the GitHub
issue scraping, resume cold-start/profile bootstrap, feature transformation,
database loading, replay, and artifact publication steps used by the Airflow
DAGs.

## Responsibilities

- `pipelines.etl.ingest` - GitHub scraping, CSV conversion, and resume ingest
- `pipelines.etl.transform` - Text normalization, keyword extraction, embeddings,
  and temporal feature engineering
- `pipelines.etl.postload` - Postgres loading, replay, and Cloud Storage
  publication

## Runtime

Airflow DAGs under `dags/` import this module directly. Keeping ETL code here
lets the `training` app focus on dataset selection, analysis, and model
training, while preserving the same production DAG behavior.

## Common entry points

```bash
uv run python -m pipelines.etl.ingest.scrape_github_issues_improved
uv run python -m pipelines.etl.postload.load_tickets --limit-per-state 20
uv run python -m pipelines.etl.postload.replay_tickets T-1 T-2
```
