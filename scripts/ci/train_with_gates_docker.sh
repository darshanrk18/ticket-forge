#!/usr/bin/env bash
set -euo pipefail

# Build and run training.cmd.train_with_gates in Docker.
#
# Usage:
#   scripts/ci/train_with_gates_docker.sh --runid local-1 --trigger workflow_dispatch --promote false
#
# Optional environment variables:
#   TRAINING_IMAGE_NAME   Docker image tag (default: ticket-forge-training)
#   TRAINING_IMAGE_BUILD  Build image before run: true|false (default: true)
#
# Notes:
# - Host ./data is mounted to /app/data
# - Host ./models is mounted to /app/models
# - Host ./data and ./models are also mounted under /app/.venv/lib/*
#   because non-editable package installs resolve repo paths there.
# - If .env exists at repo root, it is loaded via --env-file
# - Pull DVC data on host before running this script if needed

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

IMAGE_NAME="${TRAINING_IMAGE_NAME:-ticket-forge-training}"
BUILD_IMAGE="${TRAINING_IMAGE_BUILD:-true}"
RUN_ARGS=("$@")

if [[ "$#" -eq 0 ]]; then
  echo "No arguments supplied to train_with_gates."
  echo "Example:"
  echo "  scripts/ci/train_with_gates_docker.sh --runid local-1 --trigger workflow_dispatch --promote false"
  exit 1
fi

mkdir -p "${REPO_ROOT}/data" "${REPO_ROOT}/models"

if [[ "${BUILD_IMAGE}" == "true" ]]; then
  echo "Building Docker image '${IMAGE_NAME}' from docker/base.Dockerfile..."
  docker build \
    --build-arg APP_NAME=training \
    -f "${REPO_ROOT}/docker/base.Dockerfile" \
    -t "${IMAGE_NAME}" \
    "${REPO_ROOT}"
fi

env_args=()
if [[ -f "${REPO_ROOT}/.env" ]]; then
  env_args+=(--env-file "${REPO_ROOT}/.env")
fi

# Avoid noisy git lookup inside container by passing commit SHA when absent.
has_commit_sha_arg=false
for arg in "${RUN_ARGS[@]}"; do
  if [[ "${arg}" == "--commit-sha" ]]; then
    has_commit_sha_arg=true
    break
  fi
done

if [[ "${has_commit_sha_arg}" == false ]]; then
  if host_sha="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null)"; then
    RUN_ARGS+=(--commit-sha "${host_sha}")
  fi
fi

# Pass through key runtime env vars when they are present in host shell.
for key in \
  MLFLOW_TRACKING_URI \
  MLFLOW_TRACKING_URI_FROM_GCP \
  MLFLOW_CLOUD_RUN_SERVICE \
  MLFLOW_GCP_REGION \
  MLFLOW_GCP_PROJECT_ID \
  MLFLOW_TRACKING_USERNAME \
  MLFLOW_TRACKING_PASSWORD \
  MODEL_CICD_MIN_R2 \
  MODEL_CICD_MAX_MAE \
  MODEL_CICD_MAX_BIAS_RELATIVE_GAP \
  MODEL_CICD_MAX_REGRESSION_DEGRADATION \
  MODEL_CICD_BIAS_SLICES \
  MLFLOW_MAX_TUNING_RUNS \
  TICKET_FORGE_DATASET_ID; do
  if [[ -n "${!key:-}" ]]; then
    env_args+=(--env "${key}")
  fi
done

echo "Running train_with_gates in Docker..."
docker run --rm \
  -v "${REPO_ROOT}/.git:/app/.git:ro" \
  -v "${REPO_ROOT}/data:/app/data" \
  -v "${REPO_ROOT}/data:/app/.venv/lib/data" \
  -v "${REPO_ROOT}/models:/app/models" \
  -v "${REPO_ROOT}/models:/app/.venv/lib/models" \
  "${env_args[@]}" \
  "${IMAGE_NAME}" \
  -m training.cmd.train_with_gates "${RUN_ARGS[@]}"
