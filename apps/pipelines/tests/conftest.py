"""Shared fixtures for model CI/CD gate tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _fix_bash_windows_paths(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:  # type: ignore[misc]
  """Convert Windows paths to Unix paths for bash subprocess calls on Windows."""
  import platform

  if platform.system() != "Windows":
    yield
    return

  original_run = subprocess.run

  def patched_run(args: list | str, **kwargs: object) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
    def to_unix(p: object) -> str:
      # Convert Windows path to WSL path: C:\foo\bar -> /mnt/c/foo/bar
      s = str(p).replace("\\", "/")
      if len(s) >= 2 and s[1] == ":":
        drive = s[0].lower()
        s = f"/mnt/{drive}/{s[3:]}"
      return s

    if isinstance(args, list) and len(args) >= 2 and args[0] == "bash":
      unix_script = to_unix(args[1])
      # WSL bash doesn't inherit Windows env vars, so inject them explicitly
      env = kwargs.get("env") or {}  # type: ignore[assignment]
      inject = ""
      for key in ("CHANGED_FILES_OVERRIDE", "GITHUB_EVENT_NAME", "GITHUB_OUTPUT"):
        val = env.get(key, "")  # type: ignore[union-attr]
        inject += f"export {key}={val!r}; "
      args = [args[0], "-c", f"{inject}bash {unix_script}"] + list(args[2:])

    return original_run(args, **kwargs)

  import subprocess as _subprocess

  _subprocess.run = patched_run  # type: ignore[assignment]
  yield
  _subprocess.run = original_run  # type: ignore[assignment]


@pytest.fixture
def sample_gate_report(tmp_path: Path) -> Path:
  """Create a sample gate report JSON file and return its path."""
  report = {
    "run_id": "run-1",
    "candidate_model": "forest",
    "validation_gate": {"passed": True, "metrics": {}, "thresholds": {}},
    "bias_gate": {"passed": True, "slices_evaluated": []},
    "regression_guardrail": {
      "passed": True,
      "max_allowed_degradation": 0.1,
      "metric_deltas": {},
    },
    "promotion_decision": {"decision": "promoted", "promoted": True},
    "generated_at": "2026-03-23T00:00:00+00:00",
  }
  path = tmp_path / "gate_report.json"
  path.write_text(json.dumps(report), encoding="utf-8")
  return path
