FROM apache/airflow:2.10.4-python3.12

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

USER airflow
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /opt/ticket-forge

COPY --chown=airflow:0 docker/airflow/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy workspace metadata
COPY --chown=airflow:0 pyproject.toml uv.lock ./
COPY --chown=airflow:0 apps/ ./apps/
COPY --chown=airflow:0 libs/ ./libs/

# Switch to airflow user to install packages into their venv
USER airflow

# Install dependencies using uv into the airflow venv
RUN --mount=type=cache,target=/home/airflow/.cache/uv,uid=50000,gid=0 \
    uv pip install \
    -e /opt/ticket-forge/libs/shared \
    -e /opt/ticket-forge/libs/ml-core \
    -e /opt/ticket-forge/apps/training

USER root
RUN chown -R airflow:0 /opt/airflow && \
    chmod -R g+w /opt/airflow

USER airflow

ENV PYTHONPATH=/opt/ticket-forge/apps/training:/opt/ticket-forge/libs/ml-core:/opt/ticket-forge/libs/shared
ENV AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/dags
ENV AIRFLOW__CORE__LOAD_EXAMPLES=False
ENV AIRFLOW_ADMIN_USERNAME=airflow
ENV AIRFLOW_ADMIN_PASSWORD=airflow

ENTRYPOINT ["/entrypoint.sh"]

USER airflow
