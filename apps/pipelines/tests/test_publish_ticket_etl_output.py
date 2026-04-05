"""Tests for ticket_etl Cloud Storage publication helpers."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from unittest.mock import patch

import pytest


class FakeBlob:
  """In-memory blob double for Cloud Storage tests."""

  def __init__(self, name: str) -> None:
    """Initialize blob state.

    Args:
        name: Object name.
    """
    self.name = name
    self._text: str | None = None
    self._bytes: bytes | None = None

  def upload_from_filename(self, filename: str) -> None:
    """Persist uploaded file bytes from local path.

    Args:
        filename: Local file path.
    """
    self._bytes = Path(filename).read_bytes()

  def upload_from_string(self, data: str, content_type: str | None = None) -> None:
    """Persist uploaded text payload.

    Args:
        data: Text payload.
        content_type: Unused content type.
    """
    _ = content_type
    self._text = data

  def download_as_text(self) -> str:
    """Return stored text payload."""
    if self._text is not None:
      return self._text
    if self._bytes is None:
      return ""
    return self._bytes.decode("utf-8")

  def exists(self, client: object) -> bool:
    """Return true when blob has uploaded content.

    Args:
        client: Unused storage client.
    """
    _ = client
    return self._text is not None or self._bytes is not None


class FakeBucket:
  """In-memory bucket double for Cloud Storage tests."""

  def __init__(self, name: str) -> None:
    """Initialize bucket state.

    Args:
        name: Bucket name.
    """
    self.name = name
    self._blobs: dict[str, FakeBlob] = {}

  def blob(self, name: str) -> FakeBlob:
    """Return existing blob or create a new one.

    Args:
        name: Object name.
    """
    if name not in self._blobs:
      self._blobs[name] = FakeBlob(name)
    return self._blobs[name]


class FakeClient:
  """In-memory storage client double for Cloud Storage tests."""

  def __init__(self) -> None:
    """Initialize per-bucket state."""
    self._buckets: dict[str, FakeBucket] = {}

  def bucket(self, name: str) -> FakeBucket:
    """Return existing bucket or create one.

    Args:
        name: Bucket name.
    """
    if name not in self._buckets:
      self._buckets[name] = FakeBucket(name)
    return self._buckets[name]


def _write_output_file(path: Path, content: str) -> None:
  """Write a UTF-8 text file.

  Args:
      path: File path.
      content: Text content.
  """
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(content, encoding="utf-8")


def _write_gzip_output_file(path: Path, content: str) -> None:
  """Write a UTF-8 text file compressed as gzip.

  Args:
      path: File path.
      content: Text content.
  """
  path.parent.mkdir(parents=True, exist_ok=True)
  with gzip.open(path, "wt", encoding="utf-8") as file:
    file.write(content)


def _fake_upload_many_from_filenames(
  bucket: FakeBucket,
  filenames: list[str],
  *,
  source_directory: str,
  blob_name_prefix: str,
  raise_exception: bool,
) -> list[None]:
  """Emulate transfer manager uploads into fake bucket blobs.

  Args:
      bucket: Fake destination bucket.
      filenames: Relative file paths under source_directory.
      source_directory: Local base directory.
      blob_name_prefix: Prefix to prepend to destination object names.
      raise_exception: Unused transfer-manager flag.

  Returns:
      Transfer result list where None indicates success.
  """
  _ = raise_exception

  results: list[None] = []
  source_dir_path = Path(source_directory)
  for filename in filenames:
    source_path = source_dir_path / filename
    destination_blob = bucket.blob(f"{blob_name_prefix}{filename}")
    destination_blob.upload_from_filename(str(source_path))
    results.append(None)

  return results


def test_publish_ticket_etl_output_uploads_all_files_and_updates_index(
  tmp_path: Path,
) -> None:
  """Publishes full directory with compressed dataset and updates index."""
  from pipelines.etl.postload.publish_ticket_etl_output import publish_ticket_etl_output

  run_timestamp = "2026-04-03T120000Z"
  output_dir = tmp_path / f"github_issues-{run_timestamp}"
  output_dir.mkdir(parents=True)

  _write_output_file(
    output_dir / "tickets_transformed_improved.jsonl",
    '{"id": "T-1"}\n',
  )
  _write_gzip_output_file(
    output_dir / "tickets_transformed_improved.jsonl.gz",
    '{"id": "T-1"}\n',
  )
  _write_output_file(
    output_dir / "sample_weights.json",
    '{"repo": {"a": 1.0}}\n',
  )
  _write_output_file(output_dir / "reports" / "bias_report.txt", "bias report\n")

  fake_client = FakeClient()
  bucket = fake_client.bucket("test-bucket")
  bucket.blob("index.json").upload_from_string(
    json.dumps({"description": "bootstrap", "dataset_version": "v0"})
  )

  with (
    patch("pipelines.etl.postload.publish_ticket_etl_output.storage") as mock_storage,
    patch(
      "pipelines.etl.postload.publish_ticket_etl_output.transfer_manager"
    ) as mock_transfer_manager,
  ):
    mock_storage.Client.return_value = fake_client
    mock_transfer_manager.upload_many_from_filenames.side_effect = (
      _fake_upload_many_from_filenames
    )
    result = publish_ticket_etl_output(
      output_dir=output_dir,
      bucket_uri="gs://test-bucket",
      run_timestamp=run_timestamp,
    )

  dataset_id = f"github_issues-{run_timestamp}"
  assert result["dataset_id"] == dataset_id
  assert result["dataset_version"] == run_timestamp
  assert (
    result["dataset_uri"]
    == f"gs://test-bucket/{dataset_id}/tickets_transformed_improved.jsonl.gz"
  )
  assert result["index_uri"] == "gs://test-bucket/index.json"
  assert result["object_count"] == 3

  assert f"{dataset_id}/tickets_transformed_improved.jsonl.gz" in bucket._blobs
  assert f"{dataset_id}/tickets_transformed_improved.jsonl" not in bucket._blobs
  assert f"{dataset_id}/sample_weights.json" in bucket._blobs
  assert f"{dataset_id}/reports/bias_report.txt" in bucket._blobs

  updated_index = json.loads(bucket.blob("index.json").download_as_text())
  assert updated_index["current_dataset"] == result["dataset_uri"]
  assert updated_index["dataset_version"] == run_timestamp
  assert updated_index["dataset_id"] == dataset_id
  assert (
    updated_index["description"]
    == "Auto-updated by ticket_etl DAG artifact publication."
  )


def test_publish_ticket_etl_output_requires_primary_dataset_file(
  tmp_path: Path,
) -> None:
  """Fails fast when tickets_transformed_improved.jsonl.gz is missing."""
  from pipelines.etl.postload.publish_ticket_etl_output import publish_ticket_etl_output

  output_dir = tmp_path / "github_issues-2026-04-03T120500Z"
  output_dir.mkdir(parents=True)
  _write_output_file(output_dir / "sample_weights.json", "{}\n")

  with patch(
    "pipelines.etl.postload.publish_ticket_etl_output.storage"
  ) as mock_storage:
    mock_storage.Client.return_value = FakeClient()
    with pytest.raises(FileNotFoundError, match="Required dataset file not found"):
      publish_ticket_etl_output(
        output_dir=output_dir,
        bucket_uri="gs://test-bucket",
        run_timestamp="2026-04-03T120500Z",
      )


def test_publish_ticket_etl_output_rejects_bucket_object_path(tmp_path: Path) -> None:
  """Rejects bucket URIs that include object prefixes."""
  from pipelines.etl.postload.publish_ticket_etl_output import publish_ticket_etl_output

  output_dir = tmp_path / "github_issues-2026-04-03T121000Z"
  output_dir.mkdir(parents=True)
  _write_gzip_output_file(output_dir / "tickets_transformed_improved.jsonl.gz", "{}\n")

  with patch(
    "pipelines.etl.postload.publish_ticket_etl_output.storage"
  ) as mock_storage:
    mock_storage.Client.return_value = FakeClient()
    with pytest.raises(ValueError, match="must not include an object path"):
      publish_ticket_etl_output(
        output_dir=output_dir,
        bucket_uri="gs://test-bucket/some/prefix",
        run_timestamp="2026-04-03T121000Z",
      )


def test_publish_ticket_etl_output_raises_on_malformed_index(tmp_path: Path) -> None:
  """Fails when existing index.json cannot be parsed as JSON."""
  from pipelines.etl.postload.publish_ticket_etl_output import publish_ticket_etl_output

  output_dir = tmp_path / "github_issues-2026-04-03T121500Z"
  output_dir.mkdir(parents=True)
  _write_gzip_output_file(output_dir / "tickets_transformed_improved.jsonl.gz", "{}\n")

  fake_client = FakeClient()
  bucket = fake_client.bucket("test-bucket")
  bucket.blob("index.json").upload_from_string("{this-is-not-json")

  with (
    patch("pipelines.etl.postload.publish_ticket_etl_output.storage") as mock_storage,
    patch(
      "pipelines.etl.postload.publish_ticket_etl_output.transfer_manager"
    ) as mock_transfer_manager,
  ):
    mock_storage.Client.return_value = fake_client
    mock_transfer_manager.upload_many_from_filenames.side_effect = (
      _fake_upload_many_from_filenames
    )
    with pytest.raises(ValueError, match="Malformed JSON"):
      publish_ticket_etl_output(
        output_dir=output_dir,
        bucket_uri="gs://test-bucket",
        run_timestamp="2026-04-03T121500Z",
      )
