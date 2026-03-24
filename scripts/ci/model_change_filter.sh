#!/usr/bin/env bash
set -euo pipefail

# Model-impacting path filter for CI runs.
# Writes should_run and reason outputs for GitHub Actions.

EVENT_NAME="${GITHUB_EVENT_NAME:-push}"
BEFORE_SHA="${GITHUB_EVENT_BEFORE:-}"
AFTER_SHA="${GITHUB_SHA:-HEAD}"

is_model_path() {
  local path="$1"
  [[ "$path" == apps/training/* ]] || \
    [[ "$path" == libs/ml-core/* ]] || \
    [[ "$path" == libs/shared/* ]] || \
    [[ "$path" == dags/* ]] || \
    [[ "$path" == data.dvc ]] || \
    [[ "$path" == models.dvc ]] || \
    [[ "$path" == pyproject.toml ]] || \
    [[ "$path" == Justfile ]]
}

emit_output() {
  local key="$1"
  local value="$2"
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "$key=$value" >> "$GITHUB_OUTPUT"
  else
    echo "$key=$value"
  fi
}

if [[ "$EVENT_NAME" != "push" ]]; then
  emit_output "should_run" "true"
  emit_output "reason" "non-push-event-${EVENT_NAME}"
  exit 0
fi

changed_files=""
if [[ -n "${CHANGED_FILES_OVERRIDE:-}" ]]; then
  changed_files="$CHANGED_FILES_OVERRIDE"
elif [[ -n "$BEFORE_SHA" && "$BEFORE_SHA" != "0000000000000000000000000000000000000000" ]]; then
  changed_files="$(git diff --name-only "$BEFORE_SHA" "$AFTER_SHA")"
elif git rev-parse HEAD~1 &>/dev/null; then
  changed_files="$(git diff --name-only HEAD~1 HEAD)"
else
  # Single commit repo or shallow clone - can't determine previous commit.
  # Default to running training to be conservative.
  changed_files=" "
fi

if [[ -z "$changed_files" ]]; then
  emit_output "should_run" "false"
  emit_output "reason" "no-changed-files-detected"
  exit 0
fi

while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  if is_model_path "$path"; then
    emit_output "should_run" "true"
    emit_output "reason" "model-impacting-change:${path}"
    exit 0
  fi
done <<< "$changed_files"

emit_output "should_run" "false"
emit_output "reason" "no-model-impacting-changes"
