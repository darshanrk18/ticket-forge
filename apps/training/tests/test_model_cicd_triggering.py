"""Tests for model-impacting change filter script behavior."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _run_filter(changed_files: str, event: str = "push") -> str:
  """Run model change filter with override and return stdout."""
  root = Path(__file__).parents[3]
  script = root / "scripts/ci/model_change_filter.sh"
  env = os.environ.copy()
  env["CHANGED_FILES_OVERRIDE"] = changed_files
  env["GITHUB_EVENT_NAME"] = event
  # Unset GITHUB_OUTPUT so script writes to stdout instead of file
  env.pop("GITHUB_OUTPUT", None)
  result = subprocess.run(
    ["bash", str(script)],
    cwd=root,
    env=env,
    check=True,
    capture_output=True,
    text=True,
  )
  return result.stdout


def test_filter_runs_on_model_change() -> None:
  """Model-impacting paths trigger should_run=true output."""
  out = _run_filter("apps/training/training/cmd/train.py")
  assert "should_run=true" in out


def test_filter_skips_on_non_model_change() -> None:
  """Non-model changes produce should_run=false output."""
  out = _run_filter("README.md")
  assert "should_run=false" in out


def test_filter_always_runs_on_schedule() -> None:
  """Scheduled trigger always evaluates as runnable."""
  out = _run_filter("README.md", event="schedule")
  assert "should_run=true" in out
