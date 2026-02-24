# Airflow Local Run (Repo Root Compose)

Airflow now runs from the **root** `docker-compose.yml`.

## Why

To avoid duplicate Postgres definitions and split ownership.

Single source of truth:

- `docker-compose.yml` (repo root)

## Prerequisites

- Docker Desktop / Docker Compose
- GitHub token for ticket scraping (see [setup](../../apps/training/README.md)) in `.env`
- Google mail application token (see [setup](../../apps/training/README.md)) in `.env`


## Start Services

From repo root:

```powershell
docker compose up -d postgres pgadmin airflow
```

or if you have just installed:

```sh
just airflow-up
```

UIs:

- Airflow: http://localhost:8080 (user: `airflow`, pass: `airflow`)
     - login with username and password of `airflow`
- pgAdmin: http://localhost:5050
     - see [connecting section](#connecting-to-pg-admin) to view on the gui

## DAGs

### `ticket_etl` — Training Data Pipeline

**Purpose**: Complete ETL pipeline for ingesting GitHub issues, performing data quality checks, detecting and mitigating bias, and loading training data into the database. **This is the only DAG used for model training.**

**Schedule**: Monthly (`@monthly`)

**Inputs**:
> [!IMPORTANT]
> GitHub has aggressive rate limiting, and since we didn't want to break ToS with botted api keys or direct html webscraping, this pipeline is
> largely limited by API rate limits from github. If you are evaluating, you SHOULD use a value like 'limit_per_state=20' which avoids rate limit
> and shows the PoC.

- `limit_per_state` (optional): Integer to limit scraped issues per state (open/closed) for each repo (currently 3 repos). Useful for testing.

**Outputs** (saved to `./data/github_issues-<timestamp>/`):
- `tickets_raw.json.gz` — Compressed raw scraped GitHub issues
- `tickets_transformed_improved.jsonl` — Transformed feature-engineered tickets
- `tickets_transformed_improved.jsonl.gz` — Compressed transformed data
- `sample_weights.json` — Bias mitigation weights by demographic group
- `anomaly_report.txt` — Anomaly detection analysis report
- `bias_report.txt` — Bias detection and mitigation report

**Pipeline Steps**:

1. **Validate Config** — Parse runtime parameters and create timestamped output directory
2. **Scrape GitHub Issues** — GraphQL API calls to fetch issues across states (open/in-progress/closed)
3. **Transform** — Feature engineering: embeddings (384-dim vectors), keyword extraction, label parsing
4. **Anomaly Detection** — Statistical outlier detection on ticket features (fail if >30 anomalies)
5. **Bias Detection** (parallel) — Analyze assignment patterns across demographic groups
6. **Bias Mitigation** (parallel) — Calculate sample weights to counteract detected bias
7. **Prepare Bias Report** — Combine detection + mitigation into human-readable report
8. **Save Artifacts** — Persist compressed datasets, weights, and text reports to disk
9. **Load to Database** — Upsert tickets and assignments into Postgres (with profile coldstart for missing engineers)
10. **Replay Closed Tickets** — Apply Experience Decay to engineer profiles for completed assignments
11. **Send Email** — Notification with anomaly + bias reports (on success or failure)

**Database Side Effects**:
- Inserts/updates `tickets` table (with 384-dim pgvector embeddings)
- Inserts/updates `assignments` table
- Creates stub profiles in `users` table for any new assignees (no resume yet)
- Updates `profile_vector` in `users` table via Experience Decay for closed tickets

**Trigger Examples**:

```powershell
# Full production scrape (NOT RECOMMENDED UNLESS YOU HAVE A COUPLE HOURS)
docker compose exec airflow airflow dags trigger ticket_etl

# Limited test run (5 tickets per state)
docker compose exec airflow airflow dags trigger ticket_etl --conf '{"limit_per_state": 5}'
```

---

### `resume_etl` — Resume Ingestion Worker

**Purpose**: Acts as an **SQS-style worker** to process resume upload requests from the API. This is **not a training pipeline** — it's an on-demand service for handling resume ingestion triggered by API calls (e.g., when users upload resumes via the web backend).

**Schedule**: None (manual/API-triggered only)

**Inputs** (via `dag_run.conf`):
- `resumes` (array): List of resume payloads, each containing:
  - `filename`: Resume filename (e.g., `john_doe.pdf`)
  - `content_base64`: Base64-encoded PDF content
  - `github_username`: Engineer's GitHub username
  - `full_name` (optional): Engineer's full name

**Outputs**:
- No file outputs — directly updates Postgres

**Pipeline Steps**:

1. **Validate Config** — Parse resume payload array from request
2. **Ingest Resumes** — For each resume:
   - Decode base64 PDF to temporary file
   - Extract text and generate 384-dim embedding (resume base vector)
   - Extract skill keywords via regex + dictionary
   - Create or update engineer profile in `users` table
3. **Send Email** — Notification on completion (success or failure)

**Database Side Effects**:
- Inserts/updates `users` table with:
  - `resume_base_vector` (384-dim pgvector)
  - `skill_keywords` (tsvector for full-text search)
  - `profile_vector` (initialized from resume if new user)

**Trigger Example**:

```powershell
docker compose exec airflow airflow dags trigger resume_etl --conf '{"resumes":[{"filename":"john_doe.pdf","content_base64":"<base64_pdf>","github_username":"johndoe","full_name":"John Doe"}]}'
```

**Why Airflow for This?**: While this could be a simple background job, using Airflow provides retry logic, monitoring, logging, and email notifications out-of-the-box, plus it integrates with our existing infrastructure.

## Stop

```powershell
docker compose down
```

Remove volumes too:

```powershell
docker compose down -v
```


## Connecting to pg-admin

- Access pgAdmin: Open your browser to http://localhost:5050 (or the port mapped in your compose file) and log in with your configured credentials.
- Open Server Dialog: Click Add New Server on the dashboard=
- General Tab: Enter a recognizable Name for your connection (e.g., Docker DB).
- Connection Tab:

    Host name/address: Enter the exact Service Name of your Postgres container from the docker-compose.yml (e.g., postgres). Do not use localhost.
    Port: Use 5432 (the standard internal container port).
    Maintenance database: Enter postgres (or your custom POSTGRES_DB name).
    Username: Enter your ticketforge value.
    Password: Enter your root value.

- Save: Click Save. pgAdmin will now use the Docker internal network to resolve the service name and connect.
