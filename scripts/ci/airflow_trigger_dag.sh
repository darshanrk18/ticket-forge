#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <airflow-url> <dag-id> [conf-json] [run-id]"
  exit 2
fi

AIRFLOW_URL="$1"
DAG_ID="$2"
CONF_JSON="${3:-{}}"
RUN_ID="${4:-manual__$(date -u +%Y%m%dT%H%M%SZ)}"

AIRFLOW_API_USERNAME="${AIRFLOW_API_USERNAME:-${AIRFLOW_SMOKETEST_USERNAME:-}}"
AIRFLOW_API_PASSWORD="${AIRFLOW_API_PASSWORD:-${AIRFLOW_SMOKETEST_PASSWORD:-}}"

AIRFLOW_IAP_INSTANCE="${AIRFLOW_IAP_INSTANCE:-airflow-vm-prod}"
AIRFLOW_IAP_ZONE="${AIRFLOW_IAP_ZONE:-us-east1-b}"
AIRFLOW_IAP_LOCAL_PORT="${AIRFLOW_IAP_LOCAL_PORT:-18080}"

tunnel_pid=""

cleanup() {
  if [[ -n "$tunnel_pid" ]] && kill -0 "$tunnel_pid" >/dev/null 2>&1; then
    kill "$tunnel_pid" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

host_from_url() {
  local url="$1"
  local without_scheme="${url#*://}"
  local host_port="${without_scheme%%/*}"
  echo "${host_port%%:*}"
}

is_private_ipv4() {
  local host="$1"
  [[ "$host" =~ ^10\. ]] || [[ "$host" =~ ^192\.168\. ]] || [[ "$host" =~ ^172\.(1[6-9]|2[0-9]|3[0-1])\. ]]
}

start_iap_tunnel_if_needed() {
  local host
  host="$(host_from_url "$AIRFLOW_URL")"

  if ! is_private_ipv4 "$host"; then
    return 0
  fi

  if ! command -v gcloud >/dev/null 2>&1; then
    echo "Target ${host} is private, but gcloud is not available for IAP tunneling"
    return 1
  fi

  echo "Detected private Airflow URL (${host}); starting IAP tunnel via ${AIRFLOW_IAP_INSTANCE}/${AIRFLOW_IAP_ZONE}"
  gcloud compute start-iap-tunnel "$AIRFLOW_IAP_INSTANCE" 8080 \
    --zone "$AIRFLOW_IAP_ZONE" \
    --local-host-port="127.0.0.1:${AIRFLOW_IAP_LOCAL_PORT}" \
    >/tmp/airflow_iap_tunnel.log 2>&1 &
  tunnel_pid=$!

  local wait_attempts=20
  local i=0
  while (( i < wait_attempts )); do
    i=$((i + 1))
    if curl --silent --max-time 2 "http://127.0.0.1:${AIRFLOW_IAP_LOCAL_PORT}/health" >/dev/null 2>&1; then
      AIRFLOW_URL="http://127.0.0.1:${AIRFLOW_IAP_LOCAL_PORT}"
      echo "IAP tunnel ready; using ${AIRFLOW_URL}"
      return 0
    fi

    if ! kill -0 "$tunnel_pid" >/dev/null 2>&1; then
      echo "IAP tunnel process exited unexpectedly"
      if [[ -f /tmp/airflow_iap_tunnel.log ]]; then
        tail -n 20 /tmp/airflow_iap_tunnel.log || true
      fi
      return 1
    fi

    sleep 1
  done

  echo "Timed out waiting for IAP tunnel to become ready"
  if [[ -f /tmp/airflow_iap_tunnel.log ]]; then
    tail -n 20 /tmp/airflow_iap_tunnel.log || true
  fi
  return 1
}

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to build and validate the Airflow trigger payload"
  exit 1
fi

if ! echo "$CONF_JSON" | jq -e 'type == "object"' >/dev/null 2>&1; then
  echo "conf-json must be a valid JSON object, for example: '{\"force\":true}'"
  exit 2
fi

start_iap_tunnel_if_needed

TRIGGER_URL="${AIRFLOW_URL%/}/api/v1/dags/${DAG_ID}/dagRuns"
PAYLOAD="$(jq -c -n --arg run_id "$RUN_ID" --argjson conf "$CONF_JSON" '{dag_run_id: $run_id, conf: $conf}')"

auth_args=()
if [[ -n "$AIRFLOW_API_USERNAME" ]] && [[ -n "$AIRFLOW_API_PASSWORD" ]]; then
  auth_args=(--user "${AIRFLOW_API_USERNAME}:${AIRFLOW_API_PASSWORD}")
fi

http_code="$(curl --silent --show-error \
  --output /tmp/airflow_trigger_response.json \
  --write-out '%{http_code}' \
  --request POST \
  --header 'Content-Type: application/json' \
  "${auth_args[@]}" \
  --data "$PAYLOAD" \
  "$TRIGGER_URL" || true)"

if [[ "$http_code" == "200" || "$http_code" == "201" ]]; then
  echo "DAG run triggered successfully"
  jq '.' /tmp/airflow_trigger_response.json 2>/dev/null || cat /tmp/airflow_trigger_response.json
  exit 0
fi

if [[ "$http_code" == "401" ]] && [[ -z "$AIRFLOW_API_USERNAME" ]]; then
  echo "DAG trigger endpoint requires authentication (HTTP 401)."
  echo "Set AIRFLOW_API_USERNAME and AIRFLOW_API_PASSWORD (or AIRFLOW_SMOKETEST_USERNAME/PASSWORD) and retry."
  exit 1
fi

echo "Failed to trigger DAG '${DAG_ID}' (HTTP ${http_code})"
if [[ -s /tmp/airflow_trigger_response.json ]]; then
  jq '.' /tmp/airflow_trigger_response.json 2>/dev/null || cat /tmp/airflow_trigger_response.json
fi
exit 1
