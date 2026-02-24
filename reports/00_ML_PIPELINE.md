# ML Data Pipeline

Documentation and writeups for Data Pipeline deliverable.

## Setup

Use the main setup instructions in the root README for general environment setup: [README.md](../README.md) "Installation" section.

Also review setup steps listed in:
- [Training module README](../apps/training/README.md) "Setup" section
- [Docker + Airflow README](../docker/README.md) "Airflow Local Run" section

## Report

**TicketForge: MLOps Data Pipeline Documentation**

**Project Idea Recap**
TicketForge is an AI-Powered DevOps ticket assignment system that automates the time-consuming manual process of assigning tickets. It recommends optimal assignments based on engineer skills, past performance, and ticket requirements using machine learning.

Repository: [https://github.com/ALearningCurve/ticket-forge](https://github.com/ALearningCurve/ticket-forge)

Team Members: William Walling-Sotolongo, Sameer Saxena, Aditya Rajendra Prasad, Skandhan Madhusudhana, Vikas Neriyanuru, Darshan Ravindra Konnur

---

### 1 Data Acquisition

**1.1 GitHub Issues/Tickets**

Implemention: GraphQL-based GitHub Issue Scraper

Location: apps/training/training/etl/ingest/scrape_github_issues_graphql.py

Purpose: Collect ticket data from Terraform, Ansible, and Prometheus repositories for training.

Key Features include:

- It uses GitHub GraphQL API for 40x faster performance than REST
- Captures assignment timestamps from timeline events (earlier version was not capturing the same so we implemented a fix for the data ingestion)
- Collects 3 types of issues
	- Type 1: Closed issues (training data)
	- Type 2: Open and Assigned (or in-progress tickets)
	- Type 3: Open and Unassigned (or tickets in the backlog)

Data Collected:

- Total Issues: 61,271
- Closed: 58,419 (for training)
- Open + Assigned: 212 (in-progress)
- Open + Unassigned: 2,640 (backlog)
- Assignment Timestamps: 7,265 captured (11.9%)

Raw output gets stored in `data/github_issues/all_tickets.json`. The cleaned and transformed data is in `tickets_transformed_improved.jsonl`. 
The `data/` directory is tracked in DVC and also shared via OneDrive: [Submission 2 - Data Pipeline - Relevant Files](https://northeastern-my.sharepoint.com/:f:/r/personal/saxena_same_northeastern_edu/Documents/Ticket-Forge/Submission%202%20-%20Data%20Pipeline%20-%20Relevant%20Files?csf=1&web=1&e=EjH7hG)

Airflow outputs are stored in timestamped dataset containers. Example runs include [data/github_issues-2026-02-24T204631Z](../data/github_issues-2026-02-24T204631Z) with ~30,000 samples and [data/github_issues-2026-02-24T201901Z](../data/github_issues-2026-02-24T201901Z) with 17,842 tickets from the new pipeline. These containers include the full artifact set (transformed data, anomaly report, bias report, sample weights, and schema/profile outputs). The older [data/github_issues](../data/github_issues) dataset does not include bias reports, while the timestamped runs do.

Sample Data structure of one ticket in the json file.

```json
{
"id": "hashicorp_terraform-38137",
"repo": "hashicorp/terraform",
"title": "Issue title",
"body": "Issue description",
"state": "closed",
"issue_type": "closed",
"assignee": "engineer_username",
"created_at": "2026-02-09T21:41:36Z",
"assigned_at": "2026-02-10T16:35:18Z",
"closed_at": "2026-02-11T13:44:13Z",
"labels": "bug,crash",
"comments_count": 5
}
```

To reproduce the results: export `GITHUB_TOKEN=your_token` and then run the scraper using `python apps/training/training/etl/ingest/scrape_github_issues_improved.py`.

**1.2 Resume Ingress**

Implementation: API-triggered resume ingestion pipeline

Location:

* apps/backend/app/routers/resumes.py
* apps/backend/app/services/coldstart.py
* apps/airflow/dags/resume_ingest.py

Purpose: Collect and ingest engineer resume data to initialize or enrich engineer profiles used by the ticket assignment system.

Key Features include:

* Accepts batch resume uploads through POST /api/v1/resumes/upload
* Supports structured per-resume metadata:
	* filename
	* content_base64
	* github_username
	* optional full_name
* Performs end-to-end processing for each resume:
	* Base64 decode to temporary file
	* Text extraction (PDF/DOCX, OCR fallback for scanned PDFs)
	* Resume text normalization (PII cleanup)
	* Skill keyword extraction
	* 384-dimensional embedding generation (all-MiniLM-L6-v2)
* Upserts engineer records in Postgres users table with vector and keyword fields

Data Collected (per resume):

* Source file identity (filename)
* Engineer identity (github_username, optional full_name)
* Extracted normalized text (processed in pipeline)
* Extracted skill keywords
* Resume embedding vector (384-d)

Storage/Output:

* No intermediate dataset file is produced for this pipeline
* Final output is written directly to Postgres users table:
	* resume_base_vector
	* profile_vector
	* skill_keywords
	* profile metadata (github_username, full_name, timestamps)

Sample Data structure of one user in the json file.

```json
{
	"member_id": 1845627391,
	"github_username": "johndoe",
	"full_name": "John Doe",
	"resume_base_vector": "[0.0213,-0.1142,0.3378,-0.0521,...,0.0331]",
	"profile_vector": "[0.0213,-0.1142,0.3378,-0.0521,...,0.0331]",
	"skill_keywords": "'python':1 'fastapi':2 'kubernetes':3 'aws':4",
	"tickets_closed_count": 0,
	"created_at": "2026-02-24T10:42:31.512345+00:00",
	"updated_at": "2026-02-24T10:42:31.512345+00:00"
}
```

To reproduce the resume ingress results: add `DATABASE_URL` to your `.env`, then trigger the resume pipeline via `POST /api/v1/resumes/upload` with a resumes batch payload (`filename`, `content_base64`, `github_username`, optional `full_name`).

## 2 Data Preprocessing

Implementation: Multi-stage transformation pipeline

Location: apps/training/training/etl/transform/

Components:

**2.1 Text normalization - apps/training/training/etl/transform/normalize_text.py**:

Processes raw ticket text by:

- Removing markdown syntax (images, links, headers)
- Truncation of large block of code as:
	- Small sized blocks (```<15 lines```) - kept in full
	- Medium sized blocks - first 5 and last 5 lines
	- Large sized blocks - first 10 and last 10 lines
- Cleaning excessive whitespace and special characters
- Combining ticket title and body into a unified text field

Code blocks are truncated because GitHub issues often contain massive stack traces and config files that would dominate embeddings with repetitive content rather than problem descriptions. Keeping first and last lines preserves function signatures and error messages while discarding implementation details unnecessary for ticket assignment.

Future Scope: an image-to-text embedder was explored to handle screenshots and diagrams attached to GitHub issues. However, the model was too slow to run in reasonable time even with GPU acceleration. As a result, this approach has been deferred to future work.

**2.2 Temporal Features - apps/training/training/etl/transform/temporal_features.py**

Computes accurate work duration by calculating business hours from ticket assignment to closure:

- Uses assigned_at timestamp as start time when available
- Falls back to created_at for tickets assigned at creation or lacking assignment events
- Approximates business hours using a 5/7 multiplier on total elapsed hours to account for weekends
- Returns None if closed_at is missing

Example: A ticket created Feb 9 at 21:41, assigned Feb 10 at 16:35, and closed Feb 11 at 13:44 yields 15.11 business hours of actual work time, rather than the misleading 40+ hours from creation to closure.

**Note:** The current implementation uses a 5/7 approximation rather than true calendar-based weekend exclusion. A more precise implementation using actual weekday calculation is planned for future work.

**2.3 Engineer Features - apps/training/training/etl/transform/engineer_features.py**

Maps seniority levels to numeric enumerations as intern->0, junior->1, mid->2, senior->3, staff->4, principal->5

If seniority is missing or unrecognized, defaults to 2 (mid). Computes historical_avg_completion_hours per engineer by taking the mean of completion_hours_business grouped by assignee, giving a baseline of how fast each engineer historically closes tickets. If assignee or completion hours are unavailable, this field is set to None.

**Known Issue:** All tickets in the current dataset are labeled mid seniority due to a simplified heuristic. Improvement planned to infer seniority from ticket complexity, labels, or actual engineer profile data.

**2.4 Keyword Extraction - apps/training/training/etl/transform/keyword_extraction.py**

Core implementation: libs/ml-core/ml_core/keywords/extractor.py

Uses a hybrid approach to identify 300+ technical skills:

- Exact matching using a single compiled regex pattern across all skills (10-50x speedup over naive matching)
- Capitalized term extraction for acronyms and proper nouns (e.g. AWS, K8s) this is validated against the skills list before being included
- Case-insensitive matching (aws, AWS, Aws all match to the same keyword)
- Alias resolution (k8s -> kubernetes)
- Results ordered by frequency of occurrence, capped at top_k=10 keywords per ticket by default
- Singleton pattern via get_keyword_extractor() ensures the extractor is only initialized once across the pipeline

Skills categories: programming languages, frameworks, databases, cloud platforms, DevOps tools.

Example: "Fix Kubernetes ingress timeout on AWS" -> ['kubernetes', 'aws']

**2.5 Text Embeddings - apps/training/training/etl/transform/embed.py**

Core implementation: libs/ml-core/ml_core/embeddings/service.py

Converts normalized text into 384-dimensional semantic vectors using the all-MiniLM-L6-v2 pre-trained model via sentence-transformers.

Key details:

- Dynamic batch size: 512 on GPU, 128 on CPU for optimal throughput
- GPU acceleration automatically detected via torch.cuda.is_available()
- Singleton pattern via get_embedding_service() ensures the model is only loaded once, with optional force_reload if needed
- Raises ValueError on empty input text or empty batch
- get_embedding_dimension() method available to verify output shape at runtime
- Tickets and engineer profiles must use the same model for valid cosine similarity

Example: "Database timeout error" -> np.ndarray of shape (384,)

**Execution**

* Sample pipeline (for Airflow demo)

    1. Step 1: Scrape 200 tickets per state
    python apps/training/training/etl/ingest/scrape_github_issues_sample.py

    2. Step 2: Transform and generate embeddings
    python apps/training/training/etl/transform/run_transform_sample.py

* Full Pipeline

    1. Scrape all tickets:
    python apps/training/training/etl/ingest/scrape_github_issues_graphql.py
    2. Transform all tickets:
    python apps/training/training/etl/transform/run_transform.py

**Output Schema**
```json
{
	"id": "hashicorp_terraform-38137",
	"repo": "hashicorp/terraform",
	"title": "Issue title",
	"body": "Raw issue body",
	"normalized_text": "Cleaned and combined title + body",
	"keywords": ["kubernetes", "aws", "docker"],
	"embedding": [0.023, -0.041, ...],
	"embedding_model": "all-MiniLM-L6-v2",
	"completion_hours_business": 15.11,
	"assignee": "engineer_username",
	"issue_type": "closed",
	"seniority": "mid"

}
```

**Performance**

| Metric | Sample Pipeline | Full Pipeline |
| :---- | :---- | :---- |
| **Input Tickets** | ~1349 | 61271 |
| **Processing Time** | **<** 1 minute | 30-60 minutes |
| **Device** | GPU (if available) | GPU (if available) |
| **Output size** | ~5-10MB | ~1000MB |

**2.6 Resume Preprocessing - apps/training/training/etl/ingest/resume/**

Resume ingestion has its own preprocessing pipeline, separate from ticket preprocessing, because resumes are file documents (PDF/DOCX) and require document parsing plus profile initialization.

Implementation: File-based resume preprocessing with cold-start profile creation

Location:

* resume_extract.py
* resume_normalize.py
* coldstart.py

Processes raw resume files by:

* Extracting text from .pdf files using PyMuPDF
* OCR fallback via Tesseract for scanned PDFs with low machine-readable text
* Extracting .docx content from paragraphs and tables
* Removing PII-like patterns: phone numbers, emails, URLs, addresses, dates, GPA values
* Cleaning formatting artifacts and normalizing whitespace
* Extracting technical skill keywords via `ml_core.keywords.get_keyword_extractor()`
* Generating 384-dimensional embedding via `ml_core.embeddings.get_embedding_service()` (all-MiniLM-L6-v2)
* Upserting engineer records in the Postgres users table with `resume_base_vector`, `profile_vector`, `skill_keywords`, and identity metadata (`github_username`, `full_name`)

This pipeline enables cold-start profiling where new engineers can be represented in the system before they have enough ticket history, improving assignment quality from the first recommendation.

Note: Ticket embeddings and resume/profile embeddings use the same 384-dimensional model so cosine-similarity comparisons remain valid across tickets and engineers.

## 3 Test Modules

- apps/training/tests/test_scrape_github_issues_graphql.py - Validates that the GraphQL query builder correctly constructs repository-specific queries, handles pagination cursors, includes assignment timeline tracking, and requests all required issue fields for downstream processing.
- apps/training/tests/test_transform_pipeline.py - Validates the transformation pipeline by testing text normalization (markdown removal and code truncation), business-hour temporal feature computation with fallback logic, keyword extraction from text batches, and correct 384-dimensional embedding generation.
- apps/training/tests/test_bias.py - It validates data slicing across dimensions (repo, seniority, labels), metric computation, bias detection via Fairlearn, and report generation across regression and recommendation model types.
- libs/ml-core/ml_core/tests/test_embeddings.py - Tests the EmbeddingService class and verifies initialization, correct embedding shape (384-d), determinism, batch embedding, error handling for empty inputs, semantic similarity ordering, and singleton behaviour of get_embedding_service()
- libs/ml-core/ml_core/tests/test_keywords.py - Tests the KeywordExtractor class covers single/multi keyword extraction, case-insensitivity, alias resolution (e.g. K8s -> kubernetes), frequency-based ordering, top_n limiting, custom skills, and singleton behaviour of get_keyword_extractor().
- libs/ml-core/ml_core/tests/test_profiles.py - Tests EngineerProfile serialization and ProfileUpdater and validates weighted embedding updates, keyword merging/incrementing, metadata updates, decay-based resume influence, alpha validation, and the SQL query builder for profile updates.
- apps/training/tests/test_coldstart.py -  Validates resume cold-start profile creation and persistence logic, including resume text extraction, normalization with PII removal, skill keyword extraction, and 384-dimensional embedding generation. Verifies correct upsert outcomes (created, updated, skipped) across new profiles, existing stub profiles with ticket-derived data, and fully populated profiles. Also tests merge behavior ensuring resume-derived vectors and keywords combine correctly with pre-existing profile data.
- apps/web-backend/tests/test_coldstart_router.py - Validates resume upload API endpoints (POST /api/v1/resumes/upload, GET /api/v1/resumes/status/{run_id}), request schema enforcement for required and optional fields, rejection of malformed payloads, batch resume handling, and DAG trigger/status integration ensuring resume_etl is correctly invoked with the expected payload.
- apps/training/tests/test_airflow_dags.py - Validates Airflow DAG registration and loadability, confirming resume_ingest.py is discovered by the scheduler with DAG id resume_etl present in the DagBag with no import errors. Verifies task dependencies and default configuration for reliable pipeline execution.

## 4 Airflow DAGs
- In-depth DAG overview, execution flow, and design decisions are documented in [docker/README.md](../docker/README.md#dags).
- The `ticket_etl` pipeline handles GitHub ingest, transform, anomaly/bias checks, and DB load; `resume_etl` handles on-demand resume ingestion.

Ticket ETL DAG:
![Ticket ETL DAG](../docker/assets/ticket_etl_dag.png)

Resume ETL DAG:

![Resume ETL DAG](../docker/assets/resume_etl_dag.png)

## 5 Data Versioning with DVC
- Data (in `data` directory) and models (in `models` directory) are git-ignored but tracked in DVC for reproducibility and sharing.
- Setup steps (GCP auth, `dvc pull`, permission fixes) are documented in [README.md](../README.md#installation).
- Use `dvc push` after adding/updating datasets or models; Airflow runs update the data directory and must be DVC-added and pushed to persist.
- Airflow pipeline out puts to these directories new datasets/models with timestamps. This makes it easy to instantly add these files from pipeline to DVC.

## 6 Tracking and Logging
- Because we run our pipeline in airflow, we take advantage of the airflow logger to capture our logs for our ml pipeline
- For scripts that run outside of Airflow, we use a python logger (rather than print) to better capture semantic and make things like warning more visible (see apps/training/training/trainers module and libs/ml-core/ml_core/embeddings/service.py)
- For error tracking, the anomaly detection report and bias detection report are both included in the status email that Airflow sends at the end of each DAG run via send_status_email. This enables quick alerting of any important schema or data quality issues without needing to check the Airflow UI manually.
- Pipeline outputs are saved under ./data with timestamped run folders (for example [data/github_issues-2026-02-24T201901Z](../data/github_issues-2026-02-24T201901Z)) containing transformed data and bias/anomaly reports; trained models and evaluation artifacts are written under [models/2026-02-24_160024](../models/2026-02-24_160024). Both directories are tracked in DVC.

## 7 Data Schema & Statistics Generation

The project uses two complementary approaches. 

Custom SchemaValidator (libs/ml-core/ml_core/anomaly/validator.py) 
- Validates a DataFrame against a declared expected schema (column presence, type checking for str/int/float)
- Can auto-infer a schema from live data via generate_schema_from_data().
- Generate descriptive statistics per run like row/column counts, numeric stats (mean, std, min, max, missing count), and categorical value distributions via generate_statistics().

GreatExpectationsValidator  (libs/ml-core/ml_core/anomaly/ge_validator.py) 
- Auto-generates an ExpectationSuite called ticket_data_suite from the first batch of data
- Persists it to JSON via save_schema()
- Runs formal ValidationDefinition checks on subsequent batches, reporting total vs. failed expectations.

Both are integrated into the run_data_profiling script (apps/training/training/analysis/run_data_profiling.py) which also performs skew detection by comparing key column distributions between the sample dataset and the full dataset to verify representativeness. The profiling script outputs:

- ticket_schema.json: GE expectation suite
- data_profile_report.json: full profile with statistics, validation results, and skew analysis

This profiling step runs automatically in the Airflow DAG as the run_data_profiling task after every transform.


## 8 Anomaly Detection & Alerts

The anomaly detector runs three checks via a single run_all_checks() call:

1. missing values: flags any column with more than 5% nulls as problematic
2. outliers: uses z-score with a configurable threshold (default 3.0σ) on all numeric columns, capturing outlier count, percentage, and sample indices
3. invalid formats: validates that column values match their expected Python type.

These checks are run against the transformed ticket data (tickets_transformed_improved.jsonl) by run_anomaly_check.py, which also validates five key schema fields (id, repo, title, state, completion_hours_business).

The alerting system receives the anomaly report and triggers if total_anomalies >= alert_threshold (default 1). Alerts include a timestamped message listing problematic columns, missing value percentages, and outlier counts. The actual delivery is via Gmail SMTP (smtp.gmail.com:587 with STARTTLS) and the credentials are loaded from a .env file (GMAIL_APP_PASSWORD) and alerts are sent to [mlopsgroup29@gmail.com](mailto:mlopsgroup29@gmail.com) (specified with GMAIL_APP_USERNAME).

In the Airflow DAG, a soft gate is applied: if anomalies exceed the threshold, a warning email is sent immediately but the pipeline continues rather than failing. This ensures data quality issues are surfaced without blocking downstream tasks.

## 9 Pipeline Flow Optimization
- Parallelization strategy, bottlenecks, and optimization rationale are documented in [docker/README.md](../docker/README.md#pipeline-optimization).
- Refer to the execution timeline diagrams for how tasks overlap in practice.
- Refer to the linked readme for more insights into what was possible to optimize and what we struggled with.

![Ticket ETL Gantt Chart](../docker/assets/ticket_etl_gantt.png)

## 10 Data Bias Detection Using Data Slicing

Bias detection is implemented through the DataSlicer class (libs/ml-core/ml_core/bias/slicer.py). The dataset is sliced by repository, engineer seniority level, presence of a “bug” label, completion time buckets (fast, medium, slow), and extracted technical keywords.

Performance evaluation across slices is handled by the BiasAnalyzer class (libs/ml-core/ml_core/bias/analyzer.py), which uses Fairlearn’s MetricFrame to compute MAE, RMSE, and R² per subgroup. A bias condition is flagged when the relative performance gap between best and worst slice exceeds 10%.

Analysis Results on TicketForge Data:

- Repository imbalance: Ansible (33,286), Terraform (21,611), Prometheus (6,374) which is 5.2x imbalance ratio
- Completion time varies significantly by repo (Ansible avg: 3,097h, Terraform: 1,964h, Prometheus: 2,921h)
- All tickets currently labeled mid seniority (heuristic limitation see Known Issues)

Bias Mitigation (libs/ml-core/ml_core/bias/mitigation.py) provides:

- resample_underrepresented(): upsamples minority groups to match the largest group, producing tickets_balanced.jsonl (99,858 tickets)
- compute_sample_weights(): inverse frequency weighting (Prometheus: 3.20, Terraform: 0.95, Ansible: 0.61)
- adjust_predictions_for_fairness(): post-processing adjustment to reduce group level prediction disparities


Results are documented via the BiasReport class, which generates a structured plain-text report saved to bias_report.txt in the run output directory.

Bias detection is executed during ML model training, and the resulting reports and sample weights are packaged alongside model artifacts. For example, see [models/2026-02-24_160024](../models/2026-02-24_160024) (DVC access required).

## 11 Complete Pipeline Architecture
- A full architecture walkthrough is documented in [docker/README.md](../docker/README.md#dags).
- Summary: Airflow orchestrates the `ticket_etl` training pipeline (ingest, transform, quality checks, bias mitigation, DB load, and profile replay) and the `resume_etl` pipeline (on-demand resume ingestion into Postgres).

## 12 Acknowledging AI
- AI coding agents were used to code portions of this assignment (i.e. co-pilot and claude), but were used in a "human in the loop manner" rather than purely letting the AI code everything
- AI chatbots (gemini, chatgpt) were used in developing some architecture decisions
## 13 Meeting Evaluation Criteria

- Proper documentation: repository structure and setup are documented in [README.md](../README.md), with module-specific guides in [apps/training/README.md](../apps/training/README.md) and [docker/README.md](../docker/README.md).
- Modular syntax and code: pipeline stages are separated into ingest/transform modules in [apps/training/training/etl](../apps/training/training/etl) with reusable ML utilities in [libs/ml-core](../libs/ml-core).
- Pipeline orchestration (Airflow DAGs): the `ticket_etl` and `resume_etl` workflows, task flow, and design rationale are documented in [docker/README.md](../docker/README.md#dags).
- Tracking and logging: Airflow logs and status emails cover anomaly and bias reports (see [reports/00_ML_PIPELINE.md](00_ML_PIPELINE.md#6-tracking-and-logging)), with outputs stored per run under [data](../data).
- Data version control (DVC): data and models are tracked in DVC with setup and workflow in [README.md](../README.md#installation).
- Pipeline flow optimization: parallelization and gantt charts are documented in [docker/README.md](../docker/README.md#pipeline-optimization).
- Schema and statistics generation: schema profiling and statistics are described in [reports/00_ML_PIPELINE.md](00_ML_PIPELINE.md#7-data-schema--statistics-generation).
- Anomalies detection and alert generation: anomaly checks and Gmail alerts are documented in [reports/00_ML_PIPELINE.md](00_ML_PIPELINE.md#8-anomaly-detection--alerts).
- Bias detection and mitigation: data slicing and mitigation are detailed in [reports/00_ML_PIPELINE.md](00_ML_PIPELINE.md#10-data-bias-detection-using-data-slicing) with artifacts in [models/2026-02-24_160024](../models/2026-02-24_160024) (DVC access required).
- Test modules: unit tests are listed in [reports/00_ML_PIPELINE.md](00_ML_PIPELINE.md#3-test-modules).
- Reproducibility: environment setup and run instructions are in [README.md](../README.md#installation) and [docker/README.md](../docker/README.md#airflow-local-run).
- Error handling and logging: pipeline soft gates, alerts, and logging are described in [reports/00_ML_PIPELINE.md](00_ML_PIPELINE.md#8-anomaly-detection--alerts) and [reports/00_ML_PIPELINE.md](00_ML_PIPELINE.md#6-tracking-and-logging).

# 14 Summary

The TicketForge MLOps data pipeline successfully implements all required components:

* Data acquisition via GraphQL scraper (61,271 tickets from 3 repos)
* Multi-stage preprocessing with text normalization, temporal features, keyword extraction, and 384-dim embeddings
* Resume ingress via API-triggered Airflow pipeline (POST upload -> `resume_etl` DAG -> Postgres users upsert) with dedicated preprocessing (PDF/DOCX extraction, OCR fallback, PII cleanup) for cold-start engineer profiling
* Comprehensive test coverage (170 tests passing)
* Full Airflow DAG orchestration with parallel task execution
* DVC data versioning with GCP remote storage
* Airflow-native logging with email alerting for anomalies and bias reports
* Dual schema validation using custom SchemaValidator and Great Expectations, with skew detection
* Three-check anomaly detection (missing values, outliers, schema) with Gmail alerts and soft gate in DAG
* Pipeline flow optimized with parallel tasks and GraphQL batching
* Fairlearn-based bias detection and mitigation with resampling and sample weighting
