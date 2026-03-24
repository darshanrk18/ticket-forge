# Terraform

This folder manages ticket-forge infrastructure on GCP, including:

- Terraform state and DVC/model storage buckets.
- GitHub Actions Workload Identity Federation service accounts.
- A private MLflow tracking server on Cloud Run with Cloud SQL backend.

## Prerequisites

- Terraform v1.14+ installed.
- A GCP project with billing enabled.
- Auth configured via one of:
  - `gcloud auth application-default login`
  - `GOOGLE_APPLICATION_CREDENTIALS` pointing to a service account key file (set in .env file)

## First-time setup

This needs to be done once per GCP project.

1. Set the following environment variables in a .env file (hint: use `gcloud config list` to see project id):

```sh
TF_VAR_project_id=YOUR_PROJECT_ID # update to your GCP project id
TF_VAR_region=us-east1
TF_VAR_state_bucket=ticketforge-terraform
# Optional MLflow overrides
# TF_VAR_mlflow_artifact_registry_repository=mlflow-repo
# TF_VAR_mlflow_image_tag=v3.10.0
# Optional explicit override (must be docker.io, gcr.io, or docker.pkg.dev)
# TF_VAR_mlflow_server_image=us-east1-docker.pkg.dev/YOUR_PROJECT_ID/mlflow-repo/mlflow-gcp:v3.10.0
# TF_VAR_mlflow_additional_invokers=["user:you@example.com"]

# after running tf-apply, set
MLFLOW_TRACKING_URI=... # set to: $(gcloud run services describe mlflow-tracking --region us-east1 '--format=value(status.url)')
MLFLOW_TRACKING_USERNAME="admin"
MLFLOW_TRACKING_PASSWORD=...
```

### MLflow image build and push (recommended)

Following the MLflow GCP self-hosting guide, build your own image and push to
Artifact Registry before `just tf-apply`:


```bash
source .env
just tf-build-push-mlflow-image mlflow-repo v3.10.0
```

You can omit args to use defaults:

```bash
just tf-build-push-mlflow-image
```

The command enables `artifactregistry.googleapis.com` and creates the target
repository if it does not exist.

Terraform defaults now point Cloud Run at:

`<region>-docker.pkg.dev/<project>/mlflow-repo/mlflow-gcp:<tag>`

(note, if you have forked this repo, then set the `repository*` variables as well in `variables.tf`. There are helper scripts like `just get-repo-id YOUR-REPO` to help with this)

2. First-time bootstrapping if the state bucket does not exist:
- Phase 1 (Local): Comment out the backend `"gcs" {}` block in `main.tf`. Run terraform init (`just tf-init`) and terraform apply (`just tf-apply`).
- Phase 2 (Migration): Uncomment the backend `"gcs" {}` block in `main.tf`. Run terraform init again (`just tf-init`).
  - TF detects local state and a newly configured remote backend from first init. It will ask: "Do you want to copy existing state to the new backend?"; type yes and then delete local .tfstate file

3. Follow [action setup](#actions-setup) if not done so already.

## Common scripts (Just)

After the initial setup, you can run the following commands:

From repo root:

- Lint/format terraform files:
  - `just tf-lint`
- Assert correct formatting:
  - `just tf-check`
- Initialize and plan:
  - `just tf-plan`
- Initialize and apply:
  - `just tf-apply`
- Run arbitrary terraform commands:
  - `just tf` (i.e. `just tf apply`)

## Actions Setup

1. Complete the [first-time setup ](#first-time-setup) to create infrastructure
2. Then, run `just get-wif-provider`
3. Set github actions secret variables (Settings > Secrets and variables > Actions). Note that the variables for the environment are in all uppercase, but are mapped to the correct casing in the action file.

```sh
# setup to link gh -> gcp
WIF_PROVIDER_ID=${output from step 2}

# the rest are the same as the initial setup...
TF_VAR_PROJECT_ID=your-gcp-project-id
TF_VAR_STATE_BUCKET=your-tf-state-bucket-name
TF_VAR_REGION=us-east1
MLFLOW_TRACKING_URI=${terraform output -raw mlflow_tracking_uri}
MLFLOW_TRACKING_AUDIENCE=${terraform output -raw mlflow_tracking_audience}
...
```

The `ml-pipeline-sa` service account is granted `roles/run.viewer` by Terraform
so CI can resolve `MLFLOW_TRACKING_URI` via:

`gcloud run services describe mlflow-tracking --region <region> --format=value(status.url)`

## MLflow Access Model (POC)

The current POC deployment exposes the Cloud Run MLflow endpoint publicly
(`allUsers` invoker) and enables MLflow app-level auth (`--app-name basic-auth`).

For production, prefer Cloud Run IAM-private access and explicit invoker grants.

## Local Invocation (POC)

Direct endpoint usage:

```bash
export MLFLOW_TRACKING_URI="$(just tf output -raw mlflow_tracking_uri)"
```

Proxy usage (recommended for local browser testing):

```bash
gcloud run services proxy mlflow-tracking \
  --region us-east1 \
  --project ticketforge-488020 \
  --port 8080
export MLFLOW_TRACKING_URI="http://127.0.0.1:8080"

# Example: list experiments
uv run python - <<'PY'
import mlflow
print([e.name for e in mlflow.search_experiments()])
PY
```

## MLflow Credential Management

Admin username: `admin`

The Cloud Run service now bootstraps MLflow auth config at startup using
`MLFLOW_AUTH_CONFIG_PATH` and a Secret Manager-backed admin password.

- Secret name pattern: `<mlflow_service_name>-admin-password`
- Config generated at runtime: `/tmp/basic_auth.ini`
- `database_uri` in auth config points to Cloud SQL Postgres, so users/permissions
  persist across revisions.

Get the current bootstrap admin password:

```bash
gcloud secrets versions access latest \
  --secret mlflow-tracking-admin-password \
  --project ticketforge-488020
```

Important: `admin_password` in `basic_auth.ini` is used when the admin user is
first created in the auth database. After that, password changes should be done
through the API/UI and are persisted in the auth DB.

### Change Admin Password

**Method 1: REST API** (recommended for automation)

```bash
MLFLOW_URL="$(gcloud run services describe mlflow-tracking --region us-east1 '--format=value(status.url)')" # replace with output from tf-apply

curl -X PATCH "$MLFLOW_URL/api/2.0/mlflow/users/update-password" \
  -H "Content-Type: application/json" \
  -u "admin:password1234" \
  -d '{
        "username": "admin",
        "password": "secure-password"
  }'
```
