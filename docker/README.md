# Docker

This module defines docker images for running the application.

```
.
├── README.md
├── airflow/            # Airflow image and first-start configuration scripts
│   ├── Dockerfile      # Airflow container image with project configured
│   └── entrypoint.sh   # DB initialization script
└── base.Dockerfile     # Base docker image for any Python app in /apps
```

## Airflow Local Run

Airflow runs from the **root** `docker-compose.yml` to avoid duplicate Postgres definitions.

### Prerequisites

- Docker Desktop / Docker Compose
- GitHub token (see [training setup](../apps/training/README.md))
- Gmail app password (see [training setup](../apps/training/README.md))
- Both credentials in `.env` at repo root

### Start Services

From repo root:

```bash
# working
chmod +777 ./data ./models
docker compose up -d postgres pgadmin airflow

# Or use the justfile command
just airflow-up
```

**UIs:**
- Airflow: http://localhost:8080 (username: `airflow`, password: `airflow`)
- pgAdmin: http://localhost:5050 (see docker-compose.yml for credentials)

### DAGs

#### `ticket_etl` — Training Data Pipeline

**Purpose:** Complete ETL pipeline for training ML models. Ingests GitHub issues, performs quality checks, detects/mitigates bias, and loads data into Postgres.

**Schedule:** Monthly (`@monthly`)

**Runtime Parameters:**
- `limit_per_state` (optional): Limit scraped issues per state (open/closed) per repo. Use `20` for testing to avoid GitHub rate limits.

**Outputs** (saved to `./data/github_issues-<timestamp>/`):
- `tickets_raw.json.gz` — Compressed raw scraped issues
- `tickets_transformed_improved.jsonl.gz` — Feature-engineered tickets with embeddings
- `sample_weights.json` — Bias mitigation weights
- `anomaly_report.txt` — Data quality analysis
- `bias_report.txt` — Fairness analysis

**Pipeline Steps:**
NOTE: some of these steps run in parallel  (see diagram below for more details):
1. Validate config → Parse parameters, create timestamped output directory
2. Scrape GitHub → GraphQL API calls for issues across repos
3. Transform → Feature engineering (embeddings, keywords, labels)
4. Anomaly detection → Statistical outlier detection (fails if >30 anomalies)
5. Bias detection → Analyze assignment patterns across demographics
6. Bias mitigation → Calculate sample weights
7. Prepare report → Combine detection + mitigation results
8. Save artifacts → Persist datasets, weights, reports
9. Load to DB → Upsert tickets and assignments (with profile coldstart)
10. Replay tickets → Apply Experience Decay to engineer profiles
11. Send email → Notification with reports (success or failure)

**Database Side Effects:**
- Inserts/updates `tickets` table (with 384-dim pgvector embeddings)
- Inserts/updates `assignments` table
- Creates stub profiles in `users` table for new assignees
- Updates `profile_vector` via Experience Decay for closed tickets

**Trigger Examples:**

```bash
# Full production scrape (WARNING: 1-2 hours due to rate limits)
# Also might not be desired since full history can be irrelevant (i.e. tickets from 20 years
# ago likely have poor predictive power for ticekts written 6 months ago)
docker compose exec airflow airflow dags trigger ticket_etl

# Limited test run (recommended for evaluation)
## scrape 20 per state (open/close) per repo (we scrape 3) => maximum 120 tickets (~1-2 minutes to run)
docker compose exec airflow airflow dags trigger ticket_etl --conf '{"limit_per_state": 20}'
## scrape 10000 per state (open/close)  per repo (we scrape 3) => maximum 60,000 tickets (~30-60 minutes to run)
docker compose exec airflow airflow dags trigger ticket_etl --conf '{"limit_per_state": 10000 }'
```

**Pipeline Visualization:**

![Ticket ETL DAG](./assets/ticket_etl_dag.png)

**Execution Timeline:**

![Ticket ETL Gantt Chart](./assets/ticket_etl_gantt.png)

---

#### `resume_etl` — Resume Ingestion Worker

**Purpose:** SQS-style worker processing resume upload requests from the API. Not a training pipeline - handles on-demand resume ingestion triggered by web backend - hence less data validation.

**Schedule:** None (triggered by API)

**Flow:** API uploads resume → DAG triggered → Extract text → Generate embeddings → Update engineer profile in DB. This isn't used to train an ML model and we control the schema the entire time, hence the lack of bias/anomaly detection.

**Inputs** (via `dag_run.conf`):
- `resumes` (array): List of resume payloads, each containing:
  - `filename`: Resume filename (e.g., `john_doe.pdf`)
  - `content_base64`: Base64-encoded PDF content
  - `github_username`: Engineer's GitHub username
  - `full_name` (optional): Engineer's full name

**Outputs**:
- No file outputs — directly updates Postgres

**Trigger Examples:**

```bash
# Limited test run (recommended for evaluation)
cd REPO_ROOT
docker compose exec airflow airflow dags trigger resume_etl --conf "$(cat data/sample_resumes/airflow-invocation.txt)"
```

**Pipeline Visualization:**

![Resume ETL DAG](./assets/resume_etl_dag.png)

**Execution Timeline:**

![Resume ETL Gantt Chart](./assets/resume_etl_gantt.png)

---

## Pipeline Optimization

### Parallelization Strategy

Both DAGs are optimized for performance through strategic parallelization of independent tasks:

#### `ticket_etl` Parallel Execution

We optimized this pipeline to use parrallel execution! The pipeline does two big things from a highlevel: create a dataset for training and import the tickets into our OLTP database (for our web app to use).
To optimize our pipeline, after the anomaly detection step we parralelize into the creation of the training dataset and for the dabase update. Here's what it looks like in the DAG:

```
Anomaly Detection (Step 4)
        |
        ├──> | Bias Detection  |
        └──> | Bias Mitigation |
                |
            ... create dataset, create bias reports, etc. (useful for training)
        └──> ( Database Load )
                |
            ... create relationships for tickets and users in postgres, import data, "replay" ticekts (useful for our web-app)

```

**Impact:** When running parallel this saves a good amount of time (particularly since these operations are I/O heavy). On order of 60k samples this can save ~10 minutes

Note, the most time consuming steps are the web scraping and the embedding. This is clear looking at the gantt chart.
- For the web scraping, the bottleneck is the rate limiting from GitHub. To parrallelize this furhter or get speed gains we would have to generate multiple access tokens or spoof IP to get around rate limits and API quotas, but this is against Terms-of-Service, hence our reason for not going forward with that.
- For the embedding generation, the bottleneck is the fact we are running on a single machine. Because we run in a single machine, we are unable to parralelize this effectively since the main task takes most of the CPU/GPU (especially on weaker laptops). When we deploy, we will

#### `resume_etl` Parallel Execution

This pipeline runs sequentially - why? Because the bottleneck is generating the embeddings. This is a CPU/GPU intensive task which will not benefit from additional concurrency since we run on one machine, since a single embedding process can consume most resources depending on whose machine is running it.
Thus to maximize compatibility of this pipeline on different laptops we left this with no parrellization. When we deploy to GCP later on or use workers on seperate machines, we will update the pipeline.

### Resource Utilization

Parallelization leverages Airflow's built-in scheduler to distribute tasks across available workers. The Gantt charts above show the actual execution timelines, demonstrating how parallel tasks overlap and reduce total pipeline duration.

**Benefits:**
- Reduced wall-clock time for pipeline completion
- Faster feedback loops during development and testing
- Improved throughput for production workloads
