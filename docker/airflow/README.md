# Airflow Local Run (Repo Root Compose)

Airflow now runs from the **root** `docker-compose.yml`.

## Why

To avoid duplicate Postgres definitions and split ownership.

Single source of truth:

- `docker-compose.yml` (repo root)

## Prerequisites

- Docker Desktop / Docker Compose
- GitHub token for ticket scraping

Set token in your shell:

```powershell
$env:GITHUB_TOKEN = "<your_token>"
```

## Start Services

From repo root:

```powershell
docker compose up -d postgres pgadmin airflow
```

UIs:

- Airflow: http://localhost:8080 (user: `airflow`, pass: `airflow`)
- pgAdmin: http://localhost:5050

## DAGs

- `ticket_etl` (scrape -> transform -> tickets/assignments load)
- `resume_etl` (resume payload ingest)

Trigger ticket ETL:

```powershell
docker compose exec airflow airflow dags trigger ticket_etl
```

Trigger ticket ETL with test limit:

```powershell
docker compose exec airflow airflow dags trigger ticket_etl --conf '{"limit_per_state": 10}'
```

Trigger resume ingest:

```powershell
docker compose exec airflow airflow dags trigger resume_etl
```

Trigger resume ingest with payload:

```powershell
docker compose exec airflow airflow dags trigger resume_etl --conf '{"resumes":[{"filename":"john_doe.pdf","content_base64":"<base64_pdf>","github_username":"johndoe","full_name":"John Doe"}]}'
```

## Stop

```powershell
docker compose down
```

Remove volumes too:

```powershell
docker compose down -v
```


