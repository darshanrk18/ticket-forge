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
│   ├── ml-core          # Shared Logic: Data schemas, scrapers, and transforms
│   └── shared           # Utilities: Logging, DB clients, and global constants
├── terraform            # IaC: Cloud resource provisioning
├── data                 # Local Data: (Git-ignored) raw and processed datasets
├── models               # Local Model Registry: (Git-ignored) serialized weights/pickles
├── notebooks            # R&D: Data exploration and model prototyping
├── pyproject.toml       # Workspace Config: Links apps and libs via uv
├── uv.lock              # Pinned Python dependencies
├── package.json         # Node.js dependencies for JS projects
├── package-lock.json
├── Justfile             # Command runner (`just --list` for more info)
├── LICENSE
└── README.md
```

## Workspace Documentation

Each workspace has its own README with detailed setup and usage instructions:

### Applications
- [**training**](./apps/training/README.md) - ML model training pipeline for ticket time prediction
- [**web-backend**](./apps/web-backend/README.md) - FastAPI service for model serving and business logic
- [**web-frontend**](./apps/web-frontend/README.md) - Astro-based dashboard UI

### Libraries
- [**ml-core**](./libs/ml-core/README.md) - Core ML utilities and data schemas (think embedder shared across ingress and web app)
- [**shared**](./libs/shared/README.md) - Common utilities (caching, configuration, logging)

## Installation

> [!IMPORTANT]
> This project uses [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/) and [npm workspaces](https://docs.npmjs.com/cli/v8/using-npm/workspaces) since this project is laid out like a monorepo. Make sure you are familiar with both before continuing (i.e. make sure you know where to run install and package add commands)!

Here we guide you through the steps to install the tooling and dependencies needed to run our application.

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), [node 22 and npm](https://nodejs.org/en/download), and [just](https://github.com/casey/just)

2. Then run: `just` - this command installs all packages and configures the workspaces

3. Setup DVC.
   1. `gcloud auth application-default login` - authenticate your terminal using your Google Cloud account so DVC can access the configured remote storage
   1. `dvc pull` - pull down data/models tracked by DVC
   - Optional commands:
     - `dvc push` - Uploads your local DVC-tracked data and models to the remote. Run this **only after** you have added or updated data/models (e.g., after training or modifying datasets)
     - `dvc install` - optional, but adds Git hooks for DVC to automatically track changes to data and models
     - `chmod 777 ./data` and `chmod 777 ./models` so that docker volumes work correctly
   - NOTE: data directory is updated when you run the airflow pipeline. To commit these changes you must DVC add and push them up along with git PR!

4. Set environment variables in `.env` file:
   - If using terraform locally, see setup section in [**terraform**](./terraform/README.md) folder
   - If doing training ETL pipeline, see setup section in [**training**](./apps/training/README.md)

5. We have configured airflow to run locally using docker. To run airflow locally and see CLI commands for running pipelines, please follow instructions in [**airflow**](./docker/airflow/README.md)

## Usage

All usage scripts are defined in a `justfile` which can be run. Airflow commands are documented in [**airflow**](./docker/airflow/README.md).
```sh
$ just --list
Available recipes:
    default                                        # Configure repository and install dependencies

    [data-pipeline]
    train *args=''                                 # runs the training script

    [lang-agnostic]
    check                                          # runs all checks on the repo from repo-root
    install-deps                                   # install all 3rd party packages
    precommit *args='run'                          # Run pre-commit hooks

    [python]
    pycheck *args="."                              # Run all python checks on particular files and directories
    pylint *args="."                               # Runs python linting. Specify the directories/files to lint as positional args.
    pytest *args=''                                # Runs python tests. Any args are forwarded to pytest.

    [terraform]
    get-repo-id repo='alearningcurve/ticket-forge'
    get-wif-provider
    tf *args=''                                    # runs arbitray terraform command
    tf-apply *args=''                              # runs terraform apply
    tf-check                                       # assert good linting
    tf-init                                        # intializes terraform
    tf-lint                                        # format terraform
    tf-plan *args=''                               # runs terraform plan
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
