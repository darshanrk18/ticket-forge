#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <backend-url> [expected-model-version]" >&2
  exit 1
fi

backend_url="${1%/}"
expected_model_version="${2:-}"

health_file="$(mktemp)"
prediction_file="$(mktemp)"
trap 'rm -f "${health_file}" "${prediction_file}"' EXIT

health_status="$(curl -sS -o "${health_file}" -w '%{http_code}' "${backend_url}/health")"
if [[ "${health_status}" != "200" ]]; then
  echo "Backend health check failed with status ${health_status}" >&2
  cat "${health_file}" >&2
  exit 1
fi

python3 - "${health_file}" <<'PY'
import json
import sys
from pathlib import Path

payload_path = Path(sys.argv[1])
raw = payload_path.read_text(encoding="utf-8")

try:
    payload = json.loads(raw)
except json.JSONDecodeError as exc:
    raise SystemExit(
        "Backend health check did not return JSON. "
        f"Body was: {raw[:200]!r}. Error: {exc}"
    )

if payload.get("status") != "ok":
    raise SystemExit(f"Unexpected health payload: {payload}")
PY

prediction_status="$(
  curl -sS -o "${prediction_file}" -w '%{http_code}' \
    -X POST \
    -H 'Content-Type: application/json' \
    "${backend_url}/api/v1/inference/ticket-size" \
    --data-binary @- <<'JSON'
{
  "title": "Terraform apply crashes on production startup",
  "body": "The backend deploy panics after rollout and we need a fast fix.",
  "repo": "hashicorp/terraform",
  "issue_type": "bug",
  "labels": ["bug", "backend", "crash"],
  "comments_count": 4,
  "historical_avg_completion_hours": 12.5,
  "rail": "deploy_smoketest"
}
JSON
)"

if [[ "${prediction_status}" != "200" ]]; then
  echo "Backend inference smoke test failed with status ${prediction_status}" >&2
  cat "${prediction_file}" >&2
  exit 1
fi

python3 - "${prediction_file}" "${expected_model_version}" <<'PY'
import json
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_text(encoding="utf-8")
try:
    payload = json.loads(raw)
except json.JSONDecodeError as exc:
    raise SystemExit(
        "Backend inference smoke test returned non-JSON content. "
        f"Body was: {raw[:200]!r}. Error: {exc}"
    )
expected_version = sys.argv[2]

required_top_level = {
    "predicted_bucket",
    "predicted_class",
    "confidence",
    "class_probabilities",
    "latency_ms",
    "model",
    "features",
}
missing = sorted(required_top_level - payload.keys())
if missing:
    raise SystemExit(f"Prediction payload missing keys: {missing}")

if payload["predicted_bucket"] not in {"S", "M", "L", "XL"}:
    raise SystemExit(f"Unexpected bucket: {payload['predicted_bucket']}")

model = payload["model"]
if model.get("model_name") != "ticket-forge-best":
    raise SystemExit(f"Unexpected model_name: {model.get('model_name')}")

if expected_version and model.get("model_version") != expected_version:
    raise SystemExit(
        "Unexpected model_version: "
        f"{model.get('model_version')} != {expected_version}"
    )

features = payload["features"]
for key in ("keyword_count", "comments_count", "title_length", "body_length"):
    if key not in features:
        raise SystemExit(f"Feature summary missing key: {key}")

print("Backend smoke test passed")
PY
