"""Tests for serving-monitoring helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from training.cmd.monitor_model import _resolve_backend_url, _resolve_bucket_name


def test_resolve_bucket_name_from_explicit_uri() -> None:
  """Explicit bucket URIs should resolve to the bucket name."""
  assert _resolve_bucket_name("gs://ticketforge-monitoring-prod/reports") == (
    "ticketforge-monitoring-prod"
  )


def test_resolve_backend_url_prefers_explicit_value() -> None:
  """An explicit backend URL should bypass env and gcloud lookup."""
  with patch("training.cmd.monitor_model.subprocess.run") as mock_run:
    resolved = _resolve_backend_url("https://backend.example.run.app/")

  assert resolved == "https://backend.example.run.app"
  mock_run.assert_not_called()


def test_resolve_backend_url_falls_back_to_gcloud() -> None:
  """Backend URL should resolve via gcloud when args/env are absent."""
  completed = MagicMock()
  completed.returncode = 0
  completed.stdout = "https://ticketforge-backend.run.app\n"
  completed.stderr = ""

  with patch.dict("os.environ", {}, clear=False):
    with patch(
      "training.cmd.monitor_model.subprocess.run",
      return_value=completed,
    ) as mock_run:
      resolved = _resolve_backend_url(None)

  assert resolved == "https://ticketforge-backend.run.app"
  assert mock_run.call_count == 1


def test_resolve_bucket_name_requires_gs_uri() -> None:
  """Invalid monitoring bucket values should fail fast."""
  with pytest.raises(ValueError, match="Invalid bucket URI"):
    _resolve_bucket_name("ticketforge-monitoring-prod")
