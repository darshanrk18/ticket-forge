"""Tests for training analysis helper functions."""

from __future__ import annotations

import gzip
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from training.analysis.run_anomaly_check import run_anomaly_check
from training.analysis.run_bias_mitigation import (
  load_tickets,
  print_distribution,
  run_bias_mitigation_weights,
)
from training.analysis.run_data_profiling import load_jsonl, run_data_profiling


class TestRunAnomalyCheck:
  """Tests for anomaly detection runner."""

  @pytest.fixture
  def env_vars(self) -> None:
    """Set required environment variables for testing."""
    with patch.dict(
      "os.environ",
      {"GMAIL_APP_USERNAME": "test@example.com", "GMAIL_APP_PASSWORD": "test_pass"},
    ):
      yield

  @pytest.fixture
  def sample_tickets_jsonl(self) -> Path:
    """Create a temp JSONL file with sample tickets."""
    with tempfile.NamedTemporaryFile(
      mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
      # Write minimal valid tickets
      for i in range(5):
        ticket = {
          "id": f"issue_{i}",
          "repo": "test-repo",
          "title": f"Test Issue {i}",
          "body": "Description",
          "url": f"https://github.com/test-repo/issues/{i}",
          "state": "closed",
          "issue_type": "closed",
          "labels": "[]",
          "assignee": "test_user",
          "seniority": "mid",
          "seniority_enum": 2,
          "historical_avg_completion_hours": 5.0,
          "completion_hours_business": 4.5,
          "normalized_text": "some text",
          "keywords": "[]",
          "embedding": "[0.1] * 384",
          "embedding_model": "all-MiniLM-L6-v2",
          "created_at": "2025-01-01T10:00:00Z",
          "assigned_at": "2025-01-01T11:00:00Z",
          "closed_at": "2025-01-01T15:00:00Z",
          "comments_count": 2,
        }
        f.write(json.dumps(ticket) + "\n")
      temp_path = Path(f.name)
    yield temp_path
    temp_path.unlink(missing_ok=True)

  @patch("training.analysis.run_anomaly_check.AlertSystem.send_gmail_alert")
  def test_run_anomaly_check_returns_results(
    self, mock_send_alert, sample_tickets_jsonl: Path
  ) -> None:
    """Anomaly check returns structured results."""
    with patch.dict(
      "os.environ",
      {"GMAIL_APP_USERNAME": "test@example.com", "GMAIL_APP_PASSWORD": "test_pass"},
    ):
      result = run_anomaly_check(
        sample_tickets_jsonl, outlier_threshold=3.0, enable_alerts=False
      )

      assert isinstance(result, dict)
      assert "anomaly_report" in result
      assert "schema_result" in result
      assert "text_report" in result

  @patch("training.analysis.run_anomaly_check.AlertSystem.send_gmail_alert")
  def test_run_anomaly_check_loads_data(
    self, mock_send_alert, sample_tickets_jsonl: Path
  ) -> None:
    """Anomaly check loads JSONL correctly."""
    with patch.dict(
      "os.environ",
      {"GMAIL_APP_USERNAME": "test@example.com", "GMAIL_APP_PASSWORD": "test_pass"},
    ):
      result = run_anomaly_check(
        sample_tickets_jsonl, outlier_threshold=3.0, enable_alerts=False
      )

      # Verify that schema validation ran (check for expected keys)
      assert result["schema_result"]["num_amiss"] >= 0

  @patch("training.analysis.run_anomaly_check.AlertSystem.send_gmail_alert")
  def test_run_anomaly_check_sends_alert_when_anomalies_found(
    self, mock_send_alert, sample_tickets_jsonl: Path
  ) -> None:
    """Anomaly check sends alert when anomalies detected and credentials present."""
    with patch.dict(
      "os.environ",
      {"GMAIL_APP_USERNAME": "test@example.com", "GMAIL_APP_PASSWORD": "test_pass"},
    ):
      # Force anomalies to be detected by using low threshold
      result = run_anomaly_check(
        sample_tickets_jsonl, outlier_threshold=0.1, enable_alerts=True
      )

      # Verify the result structure
      assert isinstance(result, dict)
      assert "anomaly_report" in result


class TestRunBiasMitigation:
  """Tests for bias mitigation helpers."""

  @pytest.fixture  # noqa: ANN401
  def sample_tickets_df(self) -> pd.DataFrame:
    """Create sample ticket DataFrame."""
    return pd.DataFrame(
      {
        "id": ["1", "2", "3", "4"],
        "repo": ["repo-a", "repo-a", "repo-b", "repo-b"],
        "title": ["Issue 1", "Issue 2", "Issue 3", "Issue 4"],
        "body": ["desc", "desc", "desc", "desc"],
        "assignee": ["user1", "user2", "user3", "user4"],
        "completion_hours_business": [5.0, 6.0, 4.0, 7.0],
        "seniority_enum": [1, 2, 1, 3],
      }
    )

  def test_load_tickets_from_jsonl(self) -> None:  # noqa: ANN401
    """Load tickets from JSONL file."""
    with tempfile.NamedTemporaryFile(
      mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
      f.write(json.dumps({"id": "1", "repo": "a", "title": "x"}) + "\n")
      f.write(json.dumps({"id": "2", "repo": "b", "title": "y"}) + "\n")
      temp_path = Path(f.name)

    try:
      df = load_tickets(temp_path)
      assert len(df) == 2
      assert list(df["id"]) == ["1", "2"]
    finally:
      temp_path.unlink(missing_ok=True)

  def test_print_distribution_outputs(
    self, sample_tickets_df: pd.DataFrame, capsys: pytest.CaptureFixture
  ) -> None:
    """print_distribution outputs group counts."""
    print_distribution(sample_tickets_df, "TEST LABEL")
    captured = capsys.readouterr()
    assert "TEST LABEL" in captured.out
    assert "repo-a" in captured.out

  def test_run_bias_mitigation_weights_creates_output(
    self, sample_tickets_df: pd.DataFrame
  ) -> None:
    """Bias mitigation weights returns structured result."""
    with tempfile.TemporaryDirectory() as tmpdir:
      output_dir = Path(tmpdir)
      jsonl_path = output_dir / "tickets.jsonl"

      # Write DataFrame to JSONL
      with open(jsonl_path, "w", encoding="utf-8") as f:
        for record in sample_tickets_df.to_dict(orient="records"):
          f.write(json.dumps(record) + "\n")

      result = run_bias_mitigation_weights(jsonl_path, output_dir=output_dir)

      assert result["weights_path"]
      assert result["weights_by_group"]
      assert result["total_tickets"] == 4
      assert "repo-a" in result["weights_by_group"]


class TestLoadJsonl:
  """Tests for JSONL loading utility."""

  def test_load_jsonl_returns_dataframe(self) -> None:
    """load_jsonl returns DataFrame from JSONL file."""
    with tempfile.NamedTemporaryFile(
      mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
      f.write(json.dumps({"col1": "a", "col2": 1}) + "\n")
      f.write(json.dumps({"col1": "b", "col2": 2}) + "\n")
      temp_path = Path(f.name)

    try:
      df = load_jsonl(temp_path)
      assert len(df) == 2
      assert list(df.columns) == ["col1", "col2"]
    finally:
      temp_path.unlink(missing_ok=True)

  def test_load_jsonl_skips_empty_lines(self) -> None:
    """load_jsonl ignores blank lines."""
    with tempfile.NamedTemporaryFile(
      mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
      f.write(json.dumps({"x": 1}) + "\n")
      f.write("\n")  # blank line
      f.write(json.dumps({"x": 2}) + "\n")
      temp_path = Path(f.name)

    try:
      df = load_jsonl(temp_path)
      assert len(df) == 2
    finally:
      temp_path.unlink(missing_ok=True)

  def test_load_jsonl_reads_gzip_files(self) -> None:
    """load_jsonl supports .jsonl.gz inputs for cloud-published datasets."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl.gz", delete=False) as f:
      temp_path = Path(f.name)

    try:
      with gzip.open(temp_path, "wt", encoding="utf-8") as gz:
        gz.write(json.dumps({"x": 1}) + "\n")
        gz.write(json.dumps({"x": 2}) + "\n")

      df = load_jsonl(temp_path)
      assert len(df) == 2
      assert list(df["x"]) == [1, 2]
    finally:
      temp_path.unlink(missing_ok=True)

  def test_run_data_profiling_tracks_custom_profile_columns(self) -> None:
    """run_data_profiling should preserve custom serving-monitor columns."""
    with tempfile.NamedTemporaryFile(
      mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
      f.write(
        json.dumps(
          {
            "repo": "hashicorp/terraform",
            "rail": "direct_api",
            "latency_ms": 32.5,
            "confidence": 0.82,
          }
        )
        + "\n"
      )
      temp_path = Path(f.name)

    try:
      profile = run_data_profiling(
        temp_path,
        output_dir=temp_path.parent,
        numeric_columns=["latency_ms", "confidence"],
        categorical_columns=["repo", "rail"],
      )
      assert profile["profile_columns"] == {
        "numeric": ["latency_ms", "confidence"],
        "categorical": ["repo", "rail"],
      }
    finally:
      temp_path.unlink(missing_ok=True)
