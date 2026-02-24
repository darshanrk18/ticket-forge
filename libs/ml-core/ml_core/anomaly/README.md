# Anomaly Detection and Alerts

This module provides data quality monitoring through anomaly detection and automated alerting.

## Overview

Monitors data quality by detecting missing values, outliers, and schema violations. Sends alerts via Gmail when issues are detected.

## Components

### AnomalyDetector (detector.py)

Detects data quality issues including missing values above 5% threshold, outliers using z-score method (default 3 standard deviations), and invalid data formats. Returns detailed reports with counts, percentages, and problematic indices.

### SchemaValidator (validator.py)

Validates data against expected schema by checking for missing columns, extra columns, and type mismatches. Can auto-generate schema from existing data and generate descriptive statistics.

### AlertSystem (alerting.py)

Sends alerts when anomalies detected. Supports Gmail alerts with configurable thresholds. Formats reports with timestamp, anomaly counts, and actionable recommendations.

## Usage

Basic anomaly detection:
```python
from ml_core.anomaly import AnomalyDetector

detector = AnomalyDetector(outlier_threshold=3.0)
report = detector.run_all_checks(data)

if report["has_anomalies"]:
    print("Anomalies found:", report["total_anomalies"])
```

Schema validation:
```python
from ml_core.anomaly import SchemaValidator

schema = {"ticket_id": str, "completion_hours": float}
validator = SchemaValidator(schema)
result = validator.validate_schema(data)
```

Gmail alerts:
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

## Configuration

Gmail alerts require:
- Gmail account with 2FA enabled
- App password generated at https://myaccount.google.com/apppasswords
- GMAIL_APP_PASSWORD in .env file

## Anomalies Detected in Current Data

Analysis of ticket data revealed missing values in assignee field (20% of sample), outliers in completion_hours (tickets taking 1000+ hours), and all tickets labeled as mid seniority indicating mapping issues.

## Alerting Setup

Alerts sent to mlopsgroup29@gmail.com when anomalies exceed threshold. Email includes timestamp, anomaly counts, affected columns, and action items.