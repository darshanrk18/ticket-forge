# TicketForge
TicketForge is an AI-Powered DevOps ticket assignment system capable of automating the time-consuming manual process of assigning tickets. It can recommend optimal assignments based on engineer skills, past performances and ticket requirements.

## Overview
Currently, teams spend 15-20 minutes per ticket (or a backlog item) for triaging. To triage means to understand what a ticket is, what is its priority and thinking of a suitable engineer for that. Instead of thinking about how to resolve the ticket, we wasted time on triaging.
TicketForge is an AI-Powered DevOps ticket assignment system capable of automating the time-consuming manual process of assigning tickets. It can recommend optimal assignments based on engineer skills, past performances and ticket requirements.

### Folder Structure

> [!NOTE]
> Each folder contains documentation in the form of a `README.md` for how to run the apps/libs etc (or will contain it if not present already).

```
.
├── apps
│   ├── training         # ML Pipeline: Data scraping, ETL, and model training jobs
│   ├── web-backend      # API Service: Serves model predictions & business logic
│   └── web-frontend     # User Interface: Dashboard for interacting with the model
├── libs
│   ├── ml-core          # Shared Logic: Embeddings, profiles, anomaly detection
│   └── shared           # Utilities: Logging, caching, configuration
├── dags                 # Airflow DAGs: ticket_etl, resume_etl, email callbacks
├── docker               # Docker images: Airflow and base containers
├── scripts              # Initialization scripts: Postgres schema and extensions
├── terraform            # IaC: Cloud resource provisioning (GCP)
├── reports              # Project reports and writeups
├── data                 # Local Data: (Git-ignored, DVC-tracked) raw and processed datasets
├── models               # Local Model Registry: (Git-ignored, DVC-tracked) trained models
├── notebooks            # R&D: Data exploration and model prototyping
├── docker-compose.yml   # Docker Compose: Postgres, pgAdmin, Airflow orchestration
├── pyproject.toml       # Workspace Config: Links apps and libs via uv
├── uv.lock              # Pinned Python dependencies
├── package.json         # Node.js dependencies for frontend
├── package-lock.json
├── Justfile             # Command runner (`just --list` for more info)
├── LICENSE
└── README.md
```

## Workspace Documentation

Each workspace has its own README with detailed setup and usage instructions:

### Applications
- [**training**](./apps/training/README.md) - ML model training pipeline for ticket time prediction (which is run with [**docker and airflow**](./docker/README.md))
- [**web-backend**](./apps/web-backend/README.md) - FastAPI service for model serving and business logic
- [**web-frontend**](./apps/web-frontend/README.md) - Astro-based dashboard UI

### Libraries
- [**ml-core**](./libs/ml-core/README.md) - Core ML utilities and data schemas (think embedder shared across ingress and web app)
- [**shared**](./libs/shared/README.md) - Common utilities (caching, configuration, logging)

## Reports

- [**Data pipeline report**](./reports/00_DATA_PIPELINE.md) - Report and setup notes for the ticket ETL pipeline
- [**ML pipeline report**](./reports/01_ML_PIPELINE.md) - Report and setup notes for the ticket ETL pipeline


## Installation

> [!IMPORTANT]
> This project uses [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/) and [npm workspaces](https://docs.npmjs.com/cli/v8/using-npm/workspaces) since this project is laid out like a monorepo. Make sure you are familiar with both before continuing (i.e. make sure you know where to run install and package add commands)!

Here we guide you through the steps to install the tooling and dependencies needed to run our application.

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), [node 22 and npm](https://nodejs.org/en/download), and [just](https://github.com/casey/just)

2. Then run: `just` - this command installs all packages and configures the workspaces

3. Setup DVC. the `data` and `models` directories are tracked with DVC. You must follow these instructions to get access to these folders!
   1. `gcloud auth application-default login` - authenticate your terminal using your Google Cloud account so DVC can access the configured remote storage
   1. `dvc pull` - pull down data/models tracked by DVC
   1.  `chmod 777 ./data` and `chmod 777 ./models` so that docker volumes work correctly
   - Optional commands:
     - `dvc push` - Uploads your local DVC-tracked data and models to the remote. Run this **only after** you have added or updated data/models (e.g., after training or modifying datasets)
     - `dvc install` - optional, but adds Git hooks for DVC to automatically track changes to data and models
   - NOTE: data directory is updated when you run the airflow pipeline. To commit these changes you must DVC add and push them up along with git PR!

4. Set environment variables in `.env` file:
   - If using terraform locally, see setup section in [**terraform**](./terraform/README.md) folder
   - If doing training ETL pipeline, see setup section in [**training**](./apps/training/README.md)

5. We have configured airflow to run locally using docker. To run airflow locally and see CLI commands for running pipelines, please follow instructions in [**docker**](./docker/README.md)

## Usage

All workflows are exposed through the root `Justfile`.

Common development commands:

- `just` - install dependencies and bootstrap local tooling.
- `just check` - run Python checks and Terraform checks.
- `just train -- ...` - run training pipeline commands.
- `just airflow-up` - run local Airflow + Postgres + pgAdmin via Docker Compose.

GCP Airflow operations:

- `just gcp-airflow-deploy` - deploy/update Airflow VM and runtime secrets from current commit.
- `just gcp-ticketforge-schema-init` - apply ticketforge Postgres init SQL to Cloud SQL through local proxy.
- `just gcp-airflow-smoketest <url>` - run health + API smoke checks.
- `just gcp-airflow-trigger <url> <dag_id> [conf_json] [run_id]` - trigger a DAG run through the Airflow REST API.
- `just gcp-proxy airflow [local_port]` - open IAP tunnel to Airflow webserver.
- `just gcp-proxy cloud-sql [local_port]` - open Cloud SQL proxy to shared Postgres.
- `just gcp-get-conn-info` - print service URLs and credentials from Secret Manager.

Use `just --list` to view the full command set.

## Airflow Deployment (GCP)

This repository deploys Airflow to a private GCE VM using Terraform and a startup
script that checks out a GitHub ref and installs Airflow natively (no container
image rollout path for VM deploys).

1. Configure `.env` with at least `TF_VAR_project_id`, `TF_VAR_state_bucket`, and `TF_VAR_region`.
2. Export runtime integration secrets in your shell:
   - `GITHUB_TOKEN`
   - `GMAIL_APP_USERNAME`
   - `GMAIL_APP_PASSWORD`
3. Push your branch/commit to `origin`.
4. Deploy:

```sh
just gcp-airflow-deploy
```

Optional: deploy a specific git ref already available on GitHub.

```sh
AIRFLOW_REPO_REF=main just gcp-airflow-deploy
```

Smoke test and access:

```sh
just gcp-get-conn-info
just gcp-airflow-smoketest "http://10.20.0.5:8080"
just gcp-airflow-trigger "http://10.20.0.5:8080" ticket_etl '{"source":"manual"}'
just gcp-proxy airflow 18080
# then open http://127.0.0.1:18080
```

## Development

This project includes linting, type checking, and testing tools to ensure code quality.

### Running Tests

To run python tests:
```sh
just pytest [...pytest arguments]
```

### Linting

#### Python
For the python projects, we use the following tools:

- This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and code formatting.
- This project uses [Pyright](https://github.com/microsoft/pyright) for static type checking.

To invoke these just run, where you can specify a directory as optional arg

```sh
just pylint
just pylint path/to/dir
```

### Running All Checks

To run all quality checks (linting, type checking, and tests):
```sh
# Just python:
just pycheck                 # entire project
just pycheck apps/web-backend # just a single folder

# All languages
just check                   # entire project
```


## Contributing

1. Create a feature branch from `main`
2. Follow conventional commit format: `[#issue] type: description`
   - Example: `[#2] feat: implement GitHub issue scraper`
3. Ensure all tests pass (when applicable)
4. Update relevant documentation
5. Submit a pull request with completed checklist

## License

[GNU APGL](LICENSE)
