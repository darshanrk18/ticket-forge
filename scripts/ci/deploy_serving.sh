#!/usr/bin/env bash
set -euo pipefail

: "${DEPLOY_REF:=main}"
: "${DEPLOY_BACKEND:=true}"
: "${DEPLOY_FRONTEND:=true}"
: "${SERVING_MODEL_VERSION:=}"
: "${WATCH_SERVING_DEPLOY:=true}"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh must be installed and authenticated before dispatching Serving Deploy" >&2
  exit 1
fi

gh auth status >/dev/null

gh workflow run serving-deploy.yml \
  --repo "ALearningCurve/ticket-forge" \
  --ref "${DEPLOY_REF}" \
  -f "deploy_backend=${DEPLOY_BACKEND}" \
  -f "deploy_frontend=${DEPLOY_FRONTEND}" \
  -f "serving_model_version=${SERVING_MODEL_VERSION}"

echo "Serving Deploy dispatched for ref ${DEPLOY_REF}"

if [[ "${WATCH_SERVING_DEPLOY}" != "true" ]]; then
  exit 0
fi

run_id=""
for _ in $(seq 1 15); do
  run_id="$(
    gh run list \
      --repo "ALearningCurve/ticket-forge" \
      --workflow "Serving Deploy" \
      --limit 10 \
      --json databaseId,event,headBranch \
      --jq 'map(select(.event == "workflow_dispatch" and .headBranch == "'"${DEPLOY_REF}"'")) | .[0].databaseId // empty'
  )"
  if [[ -n "${run_id}" ]]; then
    break
  fi
  sleep 2
done

if [[ -z "${run_id}" ]]; then
  echo "Serving Deploy was dispatched, but no matching workflow run was found yet." >&2
  echo "Open GitHub Actions to watch progress manually." >&2
  exit 0
fi

gh run watch "${run_id}" --repo "ALearningCurve/ticket-forge"
