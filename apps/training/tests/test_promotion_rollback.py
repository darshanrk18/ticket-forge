"""Tests for safe production transition and rollback behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("mlflow")

from training.analysis.mlflow_tracking import _transition_to_production


class _Version:
  def __init__(self, version: str, stage: str) -> None:
    self.version = version
    self.current_stage = stage


def test_transition_promotes_new_before_archiving_old() -> None:
  """Existing production versions are archived only after new promotion."""
  client = MagicMock()
  client.search_model_versions.return_value = [
    _Version("1", "Production"),
    _Version("2", "None"),
  ]

  ok = _transition_to_production(client, "2")

  assert ok is True
  calls = client.transition_model_version_stage.call_args_list
  assert calls[0].kwargs["version"] == "2"
  assert calls[0].kwargs["stage"] == "Production"
  assert calls[1].kwargs["version"] == "1"
  assert calls[1].kwargs["stage"] == "Archived"
