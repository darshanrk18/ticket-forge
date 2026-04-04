#!/usr/bin/env bash
set -euo pipefail

: "${TF_VAR_project_id:?TF_VAR_project_id must be set in environment}"

connection_name="$(terraform -chdir=terraform output -raw cloud_sql_instance_connection_name)"
db_name="$(terraform -chdir=terraform output -raw cloud_sql_ticketforge_database_name)"
db_user="$(terraform -chdir=terraform output -raw cloud_sql_ticketforge_database_user)"
cloud_sql_private_ip="$(terraform -chdir=terraform output -raw cloud_sql_private_ip)"
airflow_vm_name="$(terraform -chdir=terraform output -raw airflow_vm_instance_name)"
airflow_vm_zone="${TF_VAR_zone:-us-east1-b}"
env_name="${TF_VAR_environment:-prod}"
db_password_secret_id="${TF_VAR_ticketforge_db_password_secret_id:-ticketforge-db-password-${env_name}}"
db_password="$(gcloud secrets versions access latest --project="${TF_VAR_project_id}" --secret="${db_password_secret_id}")"

proxy_bin="./cloud-sql-proxy"
if [[ ! -x "${proxy_bin}" ]]; then
  proxy_bin="cloud-sql-proxy"
fi

if ! command -v "${proxy_bin}" >/dev/null 2>&1; then
  echo "cloud-sql-proxy is required. Install it or place executable at ./cloud-sql-proxy"
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql is required. Install postgresql-client before running this script"
  exit 1
fi

cloud_sql_proxy_ip_type="${CLOUD_SQL_PROXY_IP_TYPE:-private}"
proxy_args=("${connection_name}" --address 127.0.0.1 --port 5432)
proxy_probe_timeout_seconds="${CLOUD_SQL_PSQL_PROBE_TIMEOUT:-5}"
relay_local_port="${CLOUD_SQL_RELAY_LOCAL_PORT:-15432}"
relay_proxy_script=""
relay_ssh_tunnel_pid=""
airflow_service_was_running=0
db_port="5432"

case "${cloud_sql_proxy_ip_type}" in
  private)
    proxy_args+=(--private-ip)
    ;;
  *)
    echo "Invalid CLOUD_SQL_PROXY_IP_TYPE: ${cloud_sql_proxy_ip_type} (expected 'private')"
    exit 2
    ;;
esac

proxy_log="$(mktemp -t cloud-sql-proxy.XXXXXX.log)"
probe_log="$(mktemp -t cloud-sql-proxy-probe.XXXXXX.log)"
proxy_pid=""
private_ip_reachable=0

if timeout 3 bash -c "</dev/tcp/${cloud_sql_private_ip}/5432" >/dev/null 2>&1; then
  private_ip_reachable=1
fi

cleanup() {
  kill "${proxy_pid:-}" 2>/dev/null || true
  kill "${relay_ssh_tunnel_pid:-}" 2>/dev/null || true

  if [[ "${airflow_service_was_running}" -eq 1 ]]; then
    gcloud compute ssh \
      --project="${TF_VAR_project_id}" \
      --zone="${airflow_vm_zone}" \
      --tunnel-through-iap \
      "${airflow_vm_name}" \
      --command='sudo systemctl start airflow' >/dev/null 2>&1 || true
  fi

  rm -f "${proxy_log}" "${probe_log}" "${relay_proxy_script}"
}

trap cleanup EXIT

start_direct_proxy() {
  "${proxy_bin}" "${proxy_args[@]}" >"${proxy_log}" 2>&1 &
  proxy_pid=$!
}

wait_for_proxy_ready() {
  for _ in $(seq 1 20); do
    if grep -q 'ready for new connections' "${proxy_log}"; then
      return 0
    fi

    if [[ -n "${proxy_pid}" ]] && ! kill -0 "${proxy_pid}" >/dev/null 2>&1; then
      return 1
    fi

    sleep 1
  done

  return 1
}

probe_database() {
  local port="$1"
  : >"${probe_log}"
  timeout "${proxy_probe_timeout_seconds}"s \
    env PGPASSWORD="${db_password}" \
    psql -h 127.0.0.1 -p "${port}" -U "${db_user}" -d "${db_name}" -c 'SELECT 1;' \
    >/dev/null 2>"${probe_log}"
}

start_relay_proxy() {
  if [[ "${airflow_service_was_running}" -eq 0 ]]; then
    if gcloud compute ssh \
      --project="${TF_VAR_project_id}" \
      --zone="${airflow_vm_zone}" \
      --tunnel-through-iap \
      "${airflow_vm_name}" \
      --command='sudo systemctl is-active --quiet airflow && sudo systemctl stop airflow'; then
      airflow_service_was_running=1
    fi
  fi

  relay_proxy_script="$(mktemp -t ticketforge-cloud-sql-relay.XXXXXX.sh)"
  cat >"${relay_proxy_script}" <<EOF
#!/usr/bin/env bash
set -euo pipefail

proxy_bin=/tmp/cloud-sql-proxy
if [[ ! -x "\$proxy_bin" ]]; then
  curl -fsSL -o "\$proxy_bin" https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.1/cloud-sql-proxy.linux.amd64
  chmod +x "\$proxy_bin"
fi

exec "\$proxy_bin" "${connection_name}" --private-ip --address 127.0.0.1 --port 5432
EOF
  chmod +x "${relay_proxy_script}"

  gcloud compute scp \
    --project="${TF_VAR_project_id}" \
    --zone="${airflow_vm_zone}" \
    --tunnel-through-iap \
    "${relay_proxy_script}" \
    "${airflow_vm_name}:/tmp/ticketforge-cloud-sql-relay.sh" >/dev/null

  gcloud compute ssh \
    --project="${TF_VAR_project_id}" \
    --zone="${airflow_vm_zone}" \
    --tunnel-through-iap \
    "${airflow_vm_name}" \
    --command='nohup /tmp/ticketforge-cloud-sql-relay.sh >/tmp/ticketforge-cloud-sql-relay.log 2>&1 &'

  gcloud compute ssh \
    --project="${TF_VAR_project_id}" \
    --zone="${airflow_vm_zone}" \
    --tunnel-through-iap \
    "${airflow_vm_name}" \
    -- -N -L "127.0.0.1:${relay_local_port}:127.0.0.1:5432" >/dev/null 2>&1 &
  relay_ssh_tunnel_pid=$!

  for _ in $(seq 1 5); do
    if probe_database "${relay_local_port}"; then
      return 0
    fi

    if ! kill -0 "${relay_ssh_tunnel_pid}" >/dev/null 2>&1; then
      echo "Cloud SQL relay tunnel exited unexpectedly"
      tail -n 40 "${probe_log}" || true
      return 1
    fi

    sleep 1
  done

  tail -n 40 "${probe_log}" || true
  return 1
}

connected=0
if [[ "${private_ip_reachable}" -eq 1 ]]; then
  start_direct_proxy

  if ! wait_for_proxy_ready; then
    echo "Cloud SQL proxy exited before becoming ready"
    tail -n 40 "${proxy_log}" || true
  elif probe_database "5432"; then
    connected=1
  fi
else
  echo "Local machine cannot reach the private Cloud SQL IP ${cloud_sql_private_ip}; skipping direct proxy and using an IAP relay"
fi

if [[ "${connected}" -ne 1 ]]; then
  echo "Direct private-IP proxy did not connect; falling back to an IAP relay through ${airflow_vm_name}"
  tail -n 40 "${proxy_log}" || true
  tail -n 40 "${probe_log}" || true

  kill "${proxy_pid}" 2>/dev/null || true

  if ! start_relay_proxy; then
    echo "Timed out waiting for Cloud SQL proxy database connection"
    echo "IAP relay through ${airflow_vm_name} failed"
    exit 1
  fi

  db_port="${relay_local_port}"
  connected=1
fi

for sql in scripts/postgres/init/*.sql; do
  echo "Applying ${sql}"
  PGPASSWORD="${db_password}" psql \
    -v ON_ERROR_STOP=1 \
    -h 127.0.0.1 \
    -p "${db_port}" \
    -U "${db_user}" \
    -d "${db_name}" \
    -f "${sql}"
done
