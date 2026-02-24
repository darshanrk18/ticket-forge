FROM apache/airflow:2.10.4-python3.12

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ticket-forge

COPY apps /opt/ticket-forge/apps
COPY libs /opt/ticket-forge/libs

RUN chown -R airflow:0 /opt/ticket-forge

USER airflow
RUN pip install --no-cache-dir \
    -e /opt/ticket-forge/libs/shared \
    -e /opt/ticket-forge/libs/ml-core \
    -e /opt/ticket-forge/apps/training

ENV PYTHONPATH=/opt/ticket-forge/apps/training:/opt/ticket-forge/libs/ml-core:/opt/ticket-forge/libs/shared
