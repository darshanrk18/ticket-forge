#!/bin/bash
set -e

# Ensure data directory exists; permissions/ownership should be managed by Dockerfile or host
mkdir -p /opt/ticket-forge/data
mkdir -p /opt/ticket-forge/models

AIRFLOW_ADMIN_USERNAME="${AIRFLOW_ADMIN_USERNAME:-airflow}"
AIRFLOW_ADMIN_PASSWORD="${AIRFLOW_ADMIN_PASSWORD:-airflow}"
AIRFLOW_ADMIN_FIRSTNAME="${AIRFLOW_ADMIN_FIRSTNAME:-Air}"
AIRFLOW_ADMIN_LASTNAME="${AIRFLOW_ADMIN_LASTNAME:-Flow}"
AIRFLOW_ADMIN_EMAIL="${AIRFLOW_ADMIN_EMAIL:-airflow@example.com}"

# Warn (but do not fail) if directory is not writable by current user
if [ ! -w /opt/ticket-forge/data ]; then
  echo "WARNING: /opt/ticket-forge/data is not writable by $(whoami). Airflow may fail to write data." >&2
fi
# Wait for database to be ready with retries
MAX_RETRIES=30
RETRY_COUNT=0

echo "Waiting for database to be ready..."
while ! airflow db check 2>/dev/null; do
  RETRY_COUNT=$((RETRY_COUNT + 1))
  if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    echo "ERROR: Database failed to become ready after $MAX_RETRIES attempts"
    exit 1
  fi
  echo "Database not ready yet, retrying... ($RETRY_COUNT/$MAX_RETRIES)"
  sleep 2
done

echo "Database is ready, initializing Airflow..."

# Initialize database (only runs migrations if needed)
airflow db migrate

# Create default connections
airflow connections create-default-connections

# Create admin user (ignore if already exists)
airflow users create \
  --username "$AIRFLOW_ADMIN_USERNAME" \
  --password "$AIRFLOW_ADMIN_PASSWORD" \
  --firstname "$AIRFLOW_ADMIN_FIRSTNAME" \
  --lastname "$AIRFLOW_ADMIN_LASTNAME" \
  --role Admin \
  --email "$AIRFLOW_ADMIN_EMAIL" 2>/dev/null || true

echo "Airflow initialization complete"

# If a custom command is provided (e.g., docker compose run airflow <cmd>),
# execute it directly to avoid spawning an unintended second scheduler/webserver.
if [ "$#" -gt 0 ]; then
  echo "Running custom command: $*"
  exec "$@"
fi

# Default container behavior: scheduler in background, webserver in foreground.
airflow scheduler &
exec airflow webserver
