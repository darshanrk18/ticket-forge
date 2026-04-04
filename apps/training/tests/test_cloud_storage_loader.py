"""Tests for cloud dataset loading from GCS index manifest."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from training.cloud_storage_loader import resolve_cloud_dataset


def _blob(name: str, text: str | None = None) -> MagicMock:
  blob = MagicMock()
  blob.name = name
  blob.exists.return_value = True
  blob.download_as_text.return_value = text or ""
  return blob


def test_resolve_cloud_dataset_downloads_prefix_and_returns_reference(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  """Cloud loader resolves index.json, downloads prefix, and returns metadata."""
  index = {
    "current_dataset": "gs://bucket/datasets/v1/tickets_transformed_improved.jsonl.gz",
    "dataset_version": "v1.0",
    "dataset_id": "dataset-v1",
  }

  bucket = MagicMock()
  index_blob = _blob("index.json", json.dumps(index))

  data_blob = MagicMock()
  data_blob.name = "datasets/v1/tickets_transformed_improved.jsonl.gz"

  def _download_to_filename(filename: str) -> None:
    with gzip.open(filename, "wt", encoding="utf-8") as file:
      file.write("{}\n")

  data_blob.download_to_filename.side_effect = _download_to_filename

  bucket.blob.return_value = index_blob
  bucket.list_blobs.return_value = [data_blob]

  client = MagicMock()
  client.bucket.return_value = bucket

  monkeypatch.setenv("GCS_BUCKET_NAME", "gs://bucket")

  with (
    patch("training.cloud_storage_loader.storage.Client", return_value=client),
    patch("training.cloud_storage_loader.tempfile.mkdtemp", return_value=str(tmp_path)),
  ):
    result = resolve_cloud_dataset()

  assert result.dataset_uri == index["current_dataset"]
  assert result.dataset_version == "v1.0"
  assert result.dataset_id == "dataset-v1"
  assert (result.local_directory / "tickets_transformed_improved.jsonl.gz").exists()


def test_resolve_cloud_dataset_fails_for_missing_index(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Loader fails fast when index.json is missing."""
  bucket = MagicMock()
  missing_blob = MagicMock()
  missing_blob.exists.return_value = False
  bucket.blob.return_value = missing_blob

  client = MagicMock()
  client.bucket.return_value = bucket

  monkeypatch.setenv("GCS_BUCKET_NAME", "gs://bucket")

  with patch("training.cloud_storage_loader.storage.Client", return_value=client):
    with pytest.raises(FileNotFoundError):
      resolve_cloud_dataset()
