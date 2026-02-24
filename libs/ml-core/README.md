# ML Core

Core machine learning utilities, schemas, and data transformations.

## Overview

Shared library that provides:
- **Embeddings** — Sentence transformer wrapper for 384-dim vector generation
- **Keywords** — Regex + dictionary-based skill extraction
- **Profiles** — Engineer profile management with Experience Decay
- **Anomaly Detection** — Data quality monitoring and alerting

## Structure

```
ml_core/
├── anomaly/           # Data quality monitoring
│   ├── alerting.py    # AlertSystem - Gmail notifications
│   ├── detector.py    # AnomalyDetector - outliers, missing values
│   └── validator.py   # SchemaValidator - schema enforcement
├── embeddings/        # Vector generation
│   └── service.py     # SentenceTransformer singleton (all-MiniLM-L6-v2)
├── keywords/          # Skill extraction
│   └── extractor.py   # KeywordExtractor - pattern matching
└── profiles/          # Engineer profiles
    ├── profile.py     # EngineerProfile dataclass
    └── updater.py     # ProfileUpdater - Experience Decay implementation
```

## Components

### Embeddings (`embeddings.py`)

Singleton `SentenceTransformer` wrapper using `all-MiniLM-L6-v2` for consistent 384-dimensional embeddings.

```python
from ml_core.embeddings import get_embedding_service

embedder = get_embedding_service()
vector = embedder.encode("Fix authentication bug")  # returns numpy array (384,)
```

### Keywords (`keywords.py`)

Extracts technical skills from text using pattern matching and predefined dictionaries.

```python
from ml_core.keywords import get_keyword_extractor

extractor = get_keyword_extractor()
skills = extractor.extract("Python Django REST API")  # returns list of keywords
```

### Profiles (`profiles/`)

**ProfileUpdater** — Implements Experience Decay for engineer skill profiles:
```python
profile_vector ← α · profile_vector + (1 − α) · ticket_vector
```

Supports both numpy operations and SQL query generation. Default α = 0.95.

```python
from ml_core.profiles import ProfileUpdater, EngineerProfile

updater = ProfileUpdater(decay_factor=0.95)
new_vector = updater.update_on_ticket_completion(profile_vec, ticket_vec)

# Or generate SQL for bulk updates
query = updater.build_profile_update_query(ticket_id, decay_factor=0.95)
```

### Anomaly Detection (`anomaly/`)

Data quality monitoring with automated alerting for training pipelines.

#### AnomalyDetector (`detector.py`)

Detects missing values (>5% threshold), outliers (z-score method, default 3σ), and invalid formats.

```python
from ml_core.anomaly import AnomalyDetector

detector = AnomalyDetector(outlier_threshold=3.0)
report = detector.run_all_checks(data)

if report["has_anomalies"]:
    print(f"Found {report['total_anomalies']} issues")
```

#### SchemaValidator (`validator.py`)

Validates data against expected schema (column presence, types). Auto-generates schemas from data.

```python
from ml_core.anomaly import SchemaValidator

schema = {"ticket_id": str, "completion_hours": float}
validator = SchemaValidator(schema)
result = validator.validate_schema(data)
```

#### AlertSystem (`alerting.py`)

Sends Gmail alerts when anomalies detected. Requires Gmail app password.

```python
from ml_core.anomaly import AlertSystem

alert_system = AlertSystem(alert_threshold=1)
alert_system.send_gmail_alert(
    report=report,
    recipient="team@example.com",
    sender_email="alerts@example.com",
    sender_password="app_password"
)
```

**Configuration:** Gmail alerts require 2FA-enabled account and app password (https://myaccount.google.com/apppasswords). Set `GMAIL_APP_PASSWORD` in `.env`.
