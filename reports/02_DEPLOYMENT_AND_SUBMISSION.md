# Deployment, Monitoring, and Submission Readiness

This document groups the operational deliverables for issues `#104` to `#107`.

## 1. Deployment Automation and Release Management

Primary workflows:

- `.github/workflows/ci.yml`
  - blocks deployment until repository sanity, model, backend, frontend,
    CodeQL, and Terraform checks succeed.
- `.github/workflows/airflow-deploy.yml`
  - deploys the Airflow runtime after successful `CI/CD` runs on `main`
  - records deployment traceability in `reports/runtime/airflow_deployment_report.json`
  - uploads the deployment report as a workflow artifact
- `.github/workflows/serving-deploy.yml`
  - deploys the production backend Cloud Run service on successful `CI/CD`
    runs on `main`
  - redeploys the backend automatically after successful `Model CI/CD` runs
    so promoted models become the live serving revision with a pinned
    `SERVING_MODEL_VERSION`
  - deploys the production frontend Cloud Run service on successful `CI/CD`
    runs on `main`
  - smoke tests both services and records reports in:
    - `reports/runtime/backend_deployment_report.json`
    - `reports/runtime/frontend_deployment_report.json`
- `.github/workflows/model-cicd.yml`
  - runs deterministic gated retraining and promotion
  - stores model release lineage in:
    - `models/<run_id>/gate_report.json`
    - `models/<run_id>/run_manifest.json`
    - `models/<run_id>/operations_report.json`

Release traceability now covers:

- source commit / ref
- workflow URL
- dataset source and version
- promoted model version
- deployment target and deployed runtime revision
- pinned backend serving model version for each model-triggered redeploy

## 2. Reproducibility and Verification

Fresh-machine prerequisites:

- `uv`
- `node` and `npm`
- `just`
- `terraform`
- `gh`
- `gcloud`

Required configuration and workflow artifacts:

- `README.md`
- `terraform/README.md`
- `terraform/providers.tf`
- `terraform/variables.tf`
- `terraform/main.tf`
- `terraform/secrets.tf`
- `terraform/serving.tf`
- `docker-compose.yml`
- `package.json`
- `apps/web-frontend/package.json`
- `apps/web-backend/pyproject.toml`
- `apps/web-backend/Dockerfile`
- `apps/web-frontend/Dockerfile`
- `apps/training/README.md`
- `.github/workflows/ci.yml`
- `.github/workflows/model-cicd.yml`
- `.github/workflows/model-monitoring.yml`
- `.github/workflows/airflow-deploy.yml`
- `.github/workflows/serving-deploy.yml`
- `scripts/ci/airflow_smoketest.sh`
- `scripts/ci/backend_smoketest.sh`
- `scripts/ci/deploy_serving.sh`
- `scripts/ci/frontend_smoketest.sh`
- `scripts/ci/airflow_trigger_dag.sh`
- `scripts/ci/verify_submission_ready.sh`

Core verification commands:

```bash
just install-deps
just verify-submission-ready
just gcp-airflow-deploy
just gcp-serving-deploy
just gcp-airflow-smoketest "<airflow-url>"
just gcp-backend-smoketest "<backend-url>" "<model-version>"
just gcp-frontend-smoketest "<frontend-url>"
```

`just verify-submission-ready` emits `PASS`, `WARN`, and `FAIL` lines so a clean
submission check is easy to interpret on a fresh machine.

`just gcp-serving-deploy` is the one-command serving rollout entrypoint. It
dispatches the `Serving Deploy` GitHub Actions workflow against `main`, waits
for completion by default, and lets GitHub Actions build, push, deploy, smoke
test, and report the backend/frontend release through the existing Workload
Identity Federation path.

Local retraining verification:

```bash
just train-with-gates -- --runid local-verify --trigger workflow_dispatch --source-uri dvc --promote false
```

Cloud-backed monitoring verification:

```bash
uv run python -m training.cmd.monitor_model \
  --runid monitor-local \
  --trigger workflow_dispatch \
  --trigger-reason manual-check
```

## 3. Monitoring, Drift Detection, and Retraining

Primary workflow:

- `.github/workflows/model-monitoring.yml`
  - runs on a schedule and on manual dispatch
  - resolves the deployed backend URL and exports recent serving-time inference
    events from `/api/v1/inference/monitoring/export`
  - generates a fresh `data_profile_report.json` for the serving-event stream
  - compares it against the previous monitoring baseline
  - persists:
    - `models/<run_id>/drift_report.json`
    - `models/<run_id>/operations_report.json`
    - `gs://.../monitoring/reports/<run_id>/...`
  - triggers `Model CI/CD` with `dataset_source=gcs` when drift thresholds are breached

Thresholds are versioned in code through:

- `apps/training/training/analysis/drift_detection.py`
- `apps/training/training/analysis/gate_config.py`

This keeps automated retraining aligned with the same candidate-vs-production
quality gates already used for model promotion decisions.

## 4. Notifications and Reporting

Unified operations report schema:

- `apps/training/training/analysis/ops_report.py`

Produced reports:

- deploy: `reports/runtime/airflow_deployment_report.json`
- deploy: `reports/runtime/backend_deployment_report.json`
- deploy: `reports/runtime/frontend_deployment_report.json`
- monitoring: `models/<run_id>/operations_report.json`
- training / retraining: `models/<run_id>/operations_report.json`

Retained workflow artifacts:

- `airflow-deployment-report-<github_run_id>`
- `backend-deployment-report-<github_run_id>`
- `frontend-deployment-report-<github_run_id>`
- `model-monitoring-<github_run_id>`
- `model-artifacts-<github_run_id>`
- `model-ops-artifacts-<github_run_id>`

Notification coverage:

- deploy outcome email from `.github/workflows/airflow-deploy.yml`
- deploy outcome email from `.github/workflows/serving-deploy.yml` for backend
- deploy outcome email from `.github/workflows/serving-deploy.yml` for frontend
- monitoring / drift email from `.github/workflows/model-monitoring.yml`
- training / retraining outcome email from `.github/workflows/model-cicd.yml`

Each notification includes:

- workflow run URL
- trigger source / trigger reason
- dataset source and version when applicable
- model version when applicable
- deployment target / deployed revision when applicable
- failure reasons when present

## 5. Submission Checklist

- `just verify-submission-ready` passes
- `CI/CD` passes on the final branch / PR
- `Airflow Deploy` succeeds and uploads the deployment report artifact
- `Serving Deploy` succeeds and uploads backend + frontend deployment report artifacts
- `Model Monitoring` succeeds and uploads drift + operations report artifacts
- `Model CI/CD` succeeds and uploads gate + manifest + retraining operations artifacts
- `reports/00_DATA_PIPELINE.md`, `reports/01_ML_PIPELINE.md`, and this report are committed
- board issues `#104` to `#107` can link directly to the workflows and report artifacts above
