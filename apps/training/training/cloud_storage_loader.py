"""Cloud Storage dataset resolution helpers for training runs."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from google.cloud import storage
from shared.configuration import getenv, getenv_or
from shared.logging import get_logger

logger = get_logger(__name__)

_DATASET_FILE_CANDIDATES = (
  "tickets_transformed_improved.jsonl",
  "tickets_transformed_improved.jsonl.gz",
)


@dataclass(frozen=True)
class CloudDatasetReference:
  """Resolved dataset details loaded from a Cloud Storage index file.

  Attributes:
      bucket_name: Cloud Storage bucket name.
      dataset_uri: Dataset URI from index.json.
      dataset_version: Dataset version from index.json.
      dataset_id: Dataset identifier from index.json if present.
      local_directory: Local directory containing downloaded dataset artifacts.
  """

  bucket_name: str
  dataset_uri: str
  dataset_version: str
  dataset_id: str
  local_directory: Path


def _split_gs_uri(gs_uri: str) -> tuple[str, str]:
  """Split a gs:// URI into bucket and object path.

  Args:
      gs_uri: URI like gs://bucket/path/to/object.

  Returns:
      Tuple of (bucket_name, object_path).

  Raises:
      ValueError: If URI is not a valid gs:// URI.
  """
  if not gs_uri.startswith("gs://"):
    msg = f"Invalid Cloud Storage URI: {gs_uri}"
    raise ValueError(msg)

  stripped = gs_uri.removeprefix("gs://")
  if "/" not in stripped:
    return stripped, ""

  bucket_name, object_path = stripped.split("/", 1)
  return bucket_name, object_path


def _load_index(bucket_name: str, index_path: str = "index.json") -> dict[str, object]:
  """Load and parse index.json from a Cloud Storage bucket.

  Args:
      bucket_name: Cloud Storage bucket name.
      index_path: Index object path in the bucket.

  Returns:
      Parsed JSON dictionary.

  Raises:
      FileNotFoundError: If index object is missing.
      ValueError: If index JSON is malformed or missing required keys.
  """
  client = storage.Client()
  blob = client.bucket(bucket_name).blob(index_path)

  if not blob.exists(client):
    msg = f"Missing index file gs://{bucket_name}/{index_path}"
    raise FileNotFoundError(msg)

  raw = blob.download_as_text()
  try:
    parsed = json.loads(raw)
  except json.JSONDecodeError as exc:
    msg = f"Malformed JSON in gs://{bucket_name}/{index_path}: {exc}"
    raise ValueError(msg) from exc

  current_dataset = parsed.get("current_dataset")
  dataset_version = parsed.get("dataset_version")

  if not isinstance(current_dataset, str) or not current_dataset:
    msg = "index.json must include a non-empty string field 'current_dataset'"
    raise ValueError(msg)

  if not isinstance(dataset_version, str) or not dataset_version:
    msg = "index.json must include a non-empty string field 'dataset_version'"
    raise ValueError(msg)

  return parsed


def _download_prefix(bucket_name: str, prefix: str, target_dir: Path) -> None:
  """Download all objects from a Cloud Storage prefix into a local directory.

  Args:
      bucket_name: Cloud Storage bucket name.
      prefix: Prefix path in bucket.
      target_dir: Local destination directory.
  """
  client = storage.Client()
  bucket = client.bucket(bucket_name)

  for blob in bucket.list_blobs(prefix=prefix):
    if blob.name.endswith("/"):
      continue

    relative = blob.name.removeprefix(prefix).lstrip("/")
    destination = target_dir / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(destination)


def _find_downloaded_dataset_file(local_dir: Path) -> Path | None:
  """Return the downloaded transformed dataset path when present.

  Args:
      local_dir: Local directory where the dataset prefix was downloaded.

  Returns:
      Dataset path when found, else None.
  """
  for filename in _DATASET_FILE_CANDIDATES:
    candidate = local_dir / filename
    if candidate.exists():
      return candidate
  return None


def find_downloaded_dataset_file(local_dir: Path) -> Path | None:
  """Public wrapper for locating a downloaded transformed dataset artifact."""
  return _find_downloaded_dataset_file(local_dir)


def resolve_cloud_dataset(bucket_uri: str | None = None) -> CloudDatasetReference:
  """Resolve and download a cloud dataset defined by index.json.

  Args:
      bucket_uri: Optional gs:// bucket URI. If omitted, uses GCS_BUCKET_NAME.

  Returns:
      Resolved cloud dataset reference.

  Raises:
      FileNotFoundError: If index or required dataset files are missing.
      ValueError: If index contents are malformed.
  """
  effective_bucket_uri = bucket_uri or getenv_or("GCS_BUCKET_NAME")
  if not effective_bucket_uri:
    effective_bucket_uri = getenv("GCS_BUCKET_NAME")

  bucket_name, _ = _split_gs_uri(effective_bucket_uri)
  index_data = _load_index(bucket_name)

  dataset_uri = str(index_data["current_dataset"])
  dataset_version = str(index_data["dataset_version"])
  dataset_id = str(index_data.get("dataset_id", dataset_version))

  dataset_bucket, dataset_path = _split_gs_uri(dataset_uri)
  if dataset_bucket != bucket_name:
    msg = (
      "index.json current_dataset bucket mismatch. "
      f"Expected bucket '{bucket_name}', got '{dataset_bucket}'."
    )
    raise ValueError(msg)

  local_dir = Path(tempfile.mkdtemp(prefix="ticket-forge-cloud-dataset-"))
  prefix = dataset_path.rsplit("/", 1)[0]
  _download_prefix(bucket_name, prefix, local_dir)

  expected_dataset = _find_downloaded_dataset_file(local_dir)
  if expected_dataset is None:
    msg = (
      "Downloaded cloud dataset does not include a transformed dataset artifact; "
      f"expected one of: {', '.join(_DATASET_FILE_CANDIDATES)}"
    )
    raise FileNotFoundError(msg)

  logger.info(
    "Resolved cloud dataset %s (%s) into %s",
    dataset_uri,
    dataset_version,
    local_dir,
  )

  return CloudDatasetReference(
    bucket_name=bucket_name,
    dataset_uri=dataset_uri,
    dataset_version=dataset_version,
    dataset_id=dataset_id,
    local_directory=local_dir,
  )
