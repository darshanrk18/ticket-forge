#!/usr/bin/env bash
set -euo pipefail

failures=()
warnings=()

check_file() {
  local path="$1"
  if [[ -f "$path" ]]; then
    printf 'PASS  %s\n' "$path"
  else
    printf 'FAIL  %s\n' "$path"
    failures+=("$path")
  fi
}

check_required_command() {
  local command_name="$1"
  if command -v "$command_name" >/dev/null 2>&1; then
    printf 'PASS  command:%s\n' "$command_name"
  else
    printf 'FAIL  command:%s missing from PATH\n' "$command_name"
    failures+=("command:$command_name")
  fi
}

echo "TicketForge submission-readiness verification"
echo

check_required_command uv
check_required_command node
check_required_command npm
check_required_command just
check_required_command terraform
check_required_command gh
check_required_command gcloud

echo
check_file ".github/workflows/ci.yml"
check_file ".github/workflows/model-cicd.yml"
check_file ".github/workflows/model-monitoring.yml"
check_file ".github/workflows/airflow-deploy.yml"
check_file ".github/workflows/serving-deploy.yml"
check_file "terraform/README.md"
check_file "terraform/providers.tf"
check_file "terraform/variables.tf"
check_file "terraform/main.tf"
check_file "terraform/secrets.tf"
check_file "docker-compose.yml"
check_file "apps/web-backend/Dockerfile"
check_file "apps/web-frontend/Dockerfile"
check_file "apps/training/README.md"
check_file "apps/web-backend/pyproject.toml"
check_file "apps/web-frontend/package.json"
check_file "package.json"
check_file "scripts/ci/airflow_smoketest.sh"
check_file "scripts/ci/backend_smoketest.sh"
check_file "scripts/ci/deploy_serving.sh"
check_file "scripts/ci/frontend_smoketest.sh"
check_file "scripts/ci/airflow_trigger_dag.sh"
check_file "scripts/ci/verify_submission_ready.sh"
check_file "reports/00_DATA_PIPELINE.md"
check_file "reports/01_ML_PIPELINE.md"
check_file "reports/02_DEPLOYMENT_AND_SUBMISSION.md"
check_file "README.md"

echo
if [[ -f ".env" ]]; then
  for key in TF_VAR_project_id TF_VAR_state_bucket TF_VAR_region GMAIL_APP_USERNAME GMAIL_APP_PASSWORD; do
    if grep -Eq "^${key}=" ".env"; then
      printf 'PASS  env:%s\n' "$key"
    else
      printf 'WARN  env:%s missing from .env\n' "$key"
      warnings+=("env:$key")
    fi
  done
else
  printf 'WARN  .env not found\n'
  warnings+=(".env")
fi

echo
if (( ${#failures[@]} > 0 )); then
  printf 'Submission readiness FAILED with %d missing required item(s).\n' "${#failures[@]}"
  exit 1
fi

printf 'Submission readiness PASSED.\n'
if (( ${#warnings[@]} > 0 )); then
  printf 'Warnings: %d optional item(s) still need attention.\n' "${#warnings[@]}"
fi
