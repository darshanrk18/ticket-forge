# Deployment, Monitoring, and Submission Readiness

This document is the consolidated deployment, architecture, monitoring, and
submission readiness report for the project.

## 0. Architecture Decision (Cloud Deployment)

### Context

The serving platform must host and operate:
- FastAPI backend (`web-backend`)
- lightweight inference HTTP service (`training/inference_app.py`)
- Next.js frontend (`web-frontend`)

The deployment model must be reproducible from infrastructure-as-code, validated
in CI, and operationally lightweight for a student team.

### Decision

Use Google Cloud Run for serving workloads, with Terraform-managed resources and
Artifact Registry images.

Concretely:
- App-serving stack in `terraform/app_serving.tf`:
  - `ticketforge-api`
  - `ticketforge-inference`
  - `ticketforge-web`
- Production images:
  - API: `docker/base.Dockerfile` target `cloudrun-web-backend`
  - Inference: `docker/inference.Dockerfile`
  - Frontend: `docker/frontend.Dockerfile`
- CI image build gate:
  - `.github/workflows/ci.yml` job `docker-build-apps`

### Rationale

Cloud Run provides:
- low operational overhead (no cluster/node management)
- fast rollout path for containers
- elastic scaling with pay-per-use economics
- direct integration with IAM, Secret Manager, Artifact Registry, and Terraform
- independent service release cadence (API, inference, frontend)

### Alternatives considered

1. GKE:
   - Pros: orchestration flexibility.
   - Cons: unnecessary operational complexity for project scope.
2. VM-only serving:
   - Pros: full host control.
   - Cons: manual scaling and rollout burden.
3. Single combined service:
   - Pros: fewer deploy units.
   - Cons: tighter coupling and less independent scaling.

### Consequences

Positive:
- repeatable provisioning with endpoint outputs
- clear service separation
- CI catches container regressions early

Tradeoffs:
- Cloud Run provider/runtime constraints require careful config
  (for example memory sizing and reserved env names)
- existing environments may require Terraform import of pre-existing resources

## 1. Deployment Automation and Release Management

Primary workflows:

- `.github/workflows/ci.yml`
  - blocks deployment until repository sanity, model, backend, frontend,
    CodeQL, and Terraform checks succeed.
  - includes `docker-build-apps` verification for app-serving images
    (`ticketforge-api`, `ticketforge-inference`, `ticketforge-web`)
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
- `.github/workflows/ticketforge-app-serving-deploy.yml`
  - triggers on successful `CI/CD` completion for `main`
  - builds and pushes `linux/amd64` images for API, inference, and web
  - applies `terraform/app_serving.tf` resources via Workload Identity Federation
  - validates public endpoint health checks after apply

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
- `terraform/app_serving.tf`
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
- `.github/workflows/ticketforge-app-serving-deploy.yml`
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

Local app-serving reproducibility (container only):

```bash
# builds all three Cloud Run-oriented images locally
just docker-build-apps

# optional local run examples
docker run --rm -p 8080:8080 ticketforge-api:local
docker run --rm -p 8081:8080 ticketforge-inference:local
docker run --rm -p 3000:8080 ticketforge-web:local
```

Cloud app-serving reproducibility (infra + deploy):

```bash
# CI/automation first model:
# - CI validates buildability + Terraform validate/plan
# - deploy workflow applies infra and rolls out services
#
# Manual fallback for bootstrap/debug only:
terraform -chdir=terraform apply \
  -var="enable_ticketforge_app_cloud_run=true" \
  -var="ticketforge_api_container_image=<...>" \
  -var="ticketforge_inference_container_image=<...>" \
  -var="ticketforge_web_container_image=<...>"
```

`just verify-submission-ready` emits `PASS`, `WARN`, and `FAIL` lines so a clean
submission check is easy to interpret on a fresh machine.

`just gcp-serving-deploy` remains the rollout entrypoint for the existing
backend/frontend serving stack.

`TicketForge App Serving Deploy` is the CI-driven rollout entrypoint for the
app-serving stack (`ticketforge-api`, `ticketforge-inference`, `ticketforge-web`)
and runs automatically after a successful `CI/CD` run on `main`.

Deployment ownership model:
- CI validates all required checks, including image buildability.
- GitHub Actions deployment workflows are the primary production rollout path.
- `ticketforge-app-serving-deploy.yml` is the canonical deploy automation for
  `terraform/app_serving.tf`.
- local `terraform apply` is a fallback path for bootstrap/recovery.

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

## 6. Deployment Verification Snapshot

Most recent deployed service checks:
- API: `https://ticketforge-api-r5ebf6yyyq-ue.a.run.app/health` -> `{"status":"ok"}`
- inference: `https://ticketforge-inference-r5ebf6yyyq-ue.a.run.app/health` -> `{"status":"ok"}`
- web: `https://ticketforge-web-r5ebf6yyyq-ue.a.run.app` -> `HTTP 200`
