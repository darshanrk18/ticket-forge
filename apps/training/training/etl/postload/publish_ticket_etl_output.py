"""Publish ticket_etl output artifacts to Cloud Storage.

Uploads all files from a single ticket_etl run directory into a run-specific
prefix in Cloud Storage, then updates bucket-root index.json to point training
at the newest dataset snapshot.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast

from google.cloud import storage
from google.cloud.storage import transfer_manager
from shared.configuration import getenv_or
from shared.logging import get_logger

logger = get_logger(__name__)

_REQUIRED_DATASET_FILE = "tickets_transformed_improved.jsonl.gz"
_UNCOMPRESSED_DATASET_FILE = "tickets_transformed_improved.jsonl"
_INDEX_OBJECT_NAME = "index.json"
_DEFAULT_ADC_PATH = Path("/opt/ticket-forge/data/gcp-adc.json")


class _BlobProtocol(Protocol):
  """Structural type for minimal blob behavior used by this module."""

  def exists(self, client: object) -> bool:
    """Return whether object exists in Cloud Storage."""
    ...

  def download_as_text(self) -> str:
    """Return blob contents decoded as text."""
    ...

  def upload_from_string(self, data: str, content_type: str | None = None) -> None:
    """Upload text payload to blob storage."""
    ...


class _BucketProtocol(Protocol):
  """Structural type for minimal bucket behavior used by this module."""

  def blob(self, blob_name: str) -> _BlobProtocol:
    """Return a blob handle for object operations."""
    ...


def _build_storage_client() -> storage.Client:
  """Create a Cloud Storage client using resilient credential resolution.

  Resolution order:
  1. `GOOGLE_APPLICATION_CREDENTIALS` when set and non-empty.
  2. Local default service account file at `/opt/ticket-forge/data/gcp-adc.json`.
  3. Standard Application Default Credentials fallback.

  Returns:
      Configured storage client instance.

  Raises:
      FileNotFoundError: If explicit credentials env points to a missing file.
  """
  explicit_path_raw = getenv_or("GOOGLE_APPLICATION_CREDENTIALS")
  explicit_path = explicit_path_raw.strip() if explicit_path_raw else ""

  if explicit_path:
    credentials_file = Path(explicit_path)
    if not credentials_file.is_file():
      msg = (
        f"GOOGLE_APPLICATION_CREDENTIALS points to a missing file: {credentials_file}"
      )
      raise FileNotFoundError(msg)

    logger.info("Using explicit Google credentials file: %s", credentials_file)
    return storage.Client.from_service_account_json(str(credentials_file))

  if _DEFAULT_ADC_PATH.is_file():
    logger.warning(
      "GOOGLE_APPLICATION_CREDENTIALS is unset; "
      "falling back to default credentials file: %s",
      _DEFAULT_ADC_PATH,
    )
    return storage.Client.from_service_account_json(str(_DEFAULT_ADC_PATH))

  return storage.Client()


def _parse_bucket_uri(bucket_uri: str) -> str:
  """Validate and normalize a gs:// bucket URI.

  Args:
      bucket_uri: Bucket URI in gs://<bucket> format.

  Returns:
      Normalized bucket name.

  Raises:
      ValueError: If URI is missing scheme, bucket, or contains object path.
  """
  value = bucket_uri.strip()
  if not value.startswith("gs://"):
    msg = f"Invalid bucket URI: {bucket_uri}. Expected gs://<bucket>."
    raise ValueError(msg)

  bucket_name = value.removeprefix("gs://").strip("/")
  if not bucket_name:
    msg = f"Invalid bucket URI: {bucket_uri}. Bucket name is empty."
    raise ValueError(msg)

  if "/" in bucket_name:
    msg = (
      f"Invalid bucket URI: {bucket_uri}. Bucket URI must not include an object path."
    )
    raise ValueError(msg)

  return bucket_name


def _collect_output_files(output_dir: Path) -> list[Path]:
  """Collect all output files under a run directory.

  Args:
      output_dir: Local run output directory.

  Returns:
      Sorted file list for deterministic upload order.
  """
  return sorted(path for path in output_dir.rglob("*") if path.is_file())


def _filter_upload_files(output_dir: Path, files_to_upload: list[Path]) -> list[Path]:
  """Filter files before upload.

  The uncompressed transformed dataset is retained locally for DAG tasks that
  read it directly, but cloud publication only includes the compressed variant.

  Args:
      output_dir: Local run output directory.
      files_to_upload: Candidate file list.

  Returns:
      Filtered file list for upload.
  """
  return [
    file_path
    for file_path in files_to_upload
    if file_path.relative_to(output_dir).as_posix() != _UNCOMPRESSED_DATASET_FILE
  ]


def _load_index_payload(
  bucket: _BucketProtocol,
  client: object,
  bucket_name: str,
) -> dict[str, object]:
  """Load index.json content from the bucket.

  Args:
      bucket: Cloud Storage bucket object.
      client: Cloud Storage client object.
      bucket_name: Bucket name used for error context.

  Returns:
      Parsed JSON payload or empty dict if index file is absent.

  Raises:
      ValueError: If index.json exists but is not valid JSON object.
  """
  index_blob = bucket.blob(_INDEX_OBJECT_NAME)
  if not index_blob.exists(client):
    return {}

  raw = index_blob.download_as_text()
  if not raw.strip():
    return {}

  try:
    payload = json.loads(raw)
  except json.JSONDecodeError as exc:
    msg = f"Malformed JSON in gs://{bucket_name}/{_INDEX_OBJECT_NAME}: {exc}"
    raise ValueError(msg) from exc

  if not isinstance(payload, dict):
    msg = f"Expected object JSON in gs://{bucket_name}/{_INDEX_OBJECT_NAME}"
    raise TypeError(msg)

  return payload


def _upload_output_files(
  bucket: _BucketProtocol,
  output_dir: Path,
  prefix: str,
  files_to_upload: list[Path],
) -> None:
  """Upload all output files with transfer manager.

  Args:
      bucket: Cloud Storage bucket object.
      output_dir: Local run output directory.
      prefix: Object prefix in Cloud Storage.
      files_to_upload: Files discovered under output_dir.

  Raises:
      RuntimeError: If one or more files fail to upload.
  """
  relative_paths = [
    file_path.relative_to(output_dir).as_posix() for file_path in files_to_upload
  ]
  results = transfer_manager.upload_many_from_filenames(
    bucket,
    relative_paths,
    source_directory=str(output_dir),
    blob_name_prefix=prefix,
    raise_exception=False,
  )

  failures: list[str] = []
  for relative_path, result in zip(relative_paths, results, strict=True):
    if isinstance(result, Exception):
      failures.append(f"{relative_path}: {result}")

  if failures:
    msg = "Failed uploading one or more artifacts to GCS: " + "; ".join(failures)
    raise RuntimeError(msg)


def publish_ticket_etl_output(
  output_dir: Path,
  bucket_uri: str,
  run_timestamp: str,
) -> dict[str, str | int]:
  """Publish a ticket_etl run directory and update index.json.

  Args:
      output_dir: Local output directory (for example data/github_issues-<ts>).
      bucket_uri: Cloud Storage bucket URI in gs://<bucket> format.
      run_timestamp: Run timestamp used to namespace uploaded artifacts.

  Returns:
      Publication metadata including dataset URI and upload stats.

  Raises:
      FileNotFoundError: If output directory or required dataset file is missing.
      ValueError: If bucket URI or existing index.json is invalid.
  """
  if not output_dir.exists() or not output_dir.is_dir():
    msg = f"Output directory not found: {output_dir}"
    raise FileNotFoundError(msg)

  required_dataset = output_dir / _REQUIRED_DATASET_FILE
  if not required_dataset.exists():
    msg = f"Required dataset file not found: {required_dataset}"
    raise FileNotFoundError(msg)

  files_to_upload = _collect_output_files(output_dir)
  files_to_upload = _filter_upload_files(output_dir, files_to_upload)
  if not files_to_upload:
    msg = f"No files found in output directory: {output_dir}"
    raise FileNotFoundError(msg)

  bucket_name = _parse_bucket_uri(bucket_uri)
  dataset_id = f"github_issues-{run_timestamp}"
  prefix = f"{dataset_id}/"

  client = _build_storage_client()
  bucket = cast(_BucketProtocol, client.bucket(bucket_name))

  _upload_output_files(bucket, output_dir, prefix, files_to_upload)
  bytes_uploaded = sum(file_path.stat().st_size for file_path in files_to_upload)

  dataset_uri = f"gs://{bucket_name}/{prefix}{_REQUIRED_DATASET_FILE}"

  index_payload = _load_index_payload(bucket, client, bucket_name)
  index_payload.update(
    {
      "current_dataset": dataset_uri,
      "dataset_version": run_timestamp,
      "dataset_id": dataset_id,
      "created_date": datetime.now(timezone.utc).isoformat(),
      "description": "Auto-updated by ticket_etl DAG artifact publication.",
    }
  )

  index_blob = bucket.blob(_INDEX_OBJECT_NAME)
  index_blob.upload_from_string(
    json.dumps(index_payload, indent=2, sort_keys=True) + "\n",
    content_type="application/json",
  )

  logger.info(
    "Published ticket_etl output %s to gs://%s/%s",
    output_dir,
    bucket_name,
    prefix,
  )

  return {
    "bucket_name": bucket_name,
    "dataset_id": dataset_id,
    "dataset_uri": dataset_uri,
    "dataset_version": run_timestamp,
    "index_uri": f"gs://{bucket_name}/{_INDEX_OBJECT_NAME}",
    "object_prefix": f"gs://{bucket_name}/{prefix}",
    "object_count": len(files_to_upload),
    "bytes_uploaded": bytes_uploaded,
  }
