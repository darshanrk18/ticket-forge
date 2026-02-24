# Terraform

This folder manages a demo GCP storage bucket and uses a GCS backend for state.

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
```

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
...
```
