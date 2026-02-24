set dotenv-load := true

# Configure repository and install dependencies
default: install-deps

# install all 3rd party packages
[group('lang-agnostic')]
install-deps:
    uv sync --all-packages
    npm i
    uv run pre-commit install
    uv tool install 'dvc[gs]'

# Runs python tests. Any args are forwarded to pytest.
[group('python')]
[positional-arguments]
pytest *args='':
    uv run pytest "$@"

# Runs python linting. Specify the directories/files to lint as positional args.
[group('python')]
[positional-arguments]
pylint *args=".":
    uv run ruff check --fix "$@"
    uv run ruff format "$@"
    # uv run pyright "$@"

# Run all python checks on particular files and directories
[group('python')]
pycheck *args=".":
    just pylint "$@"
    just pytest "$@"

# Run pre-commit hooks
[group('lang-agnostic')]
[positional-arguments]
precommit *args='run':
    uv run pre-commit "$@"

# runs all checks on the repo from repo-root
[group('lang-agnostic')]
check:
    just pycheck .

    @if [ -d "terraform/.terraform" ]; then \
        just tf-check; \
    else \
        echo "tf not initialized "; \
    fi

# runs the training script
[group('data-pipeline')]
[positional-arguments]
train *args='':
    uv run python -m training.cmd.train {{ args }}

# initializes terraform
[group('terraform')]
tf-init:
    terraform -chdir=terraform init -backend-config="bucket=${TF_VAR_state_bucket}"

# format terraform
[group('terraform')]
tf-lint:
    terraform -chdir=terraform fmt -recursive

# assert good linting
[group('terraform')]
tf-check:
    terraform -chdir=terraform fmt -check -recursive
    terraform -chdir=terraform validate

# runs terraform plan
[group('terraform')]
[positional-arguments]
tf-plan *args='':
    terraform -chdir=terraform plan {{ args }}

# runs terraform apply
[group('terraform')]
[positional-arguments]
tf-apply *args='':
    terraform -chdir=terraform apply {{ args }}

# runs arbitrary terraform command
[group('terraform')]
[positional-arguments]
tf *args='':
    terraform -chdir=terraform {{ args }}

[group('terraform')]
get-wif-provider:
    @gcloud iam workload-identity-pools providers describe github-provider \
        --project=${TF_VAR_project_id} --location="global" --workload-identity-pool=github-actions-pool \
        --format="value(name)"

[group('terraform')]
get-repo-id repo='alearningcurve/ticket-forge':
    @gh api -H "Accept: application/vnd.github+json" repos/{{ repo }} | jq .id

# starts airflow docker environment
[group('airflow')]
airflow-up:
    chmod +777 ./data ./models
    docker compose up -d --build postgres pgadmin airflow
