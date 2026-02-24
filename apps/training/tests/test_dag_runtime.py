"""Runtime tests for Airflow DAG helper functions."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DAGS_DIR = REPO_ROOT / "dags"


class DummyTaskInstance:
  """Minimal task instance stub for XCom usage."""

  def __init__(self) -> None:
    """Initialize XCom dict."""
    self.xcom: dict[str, Any] = {}

  def xcom_push(self, *, key: str, value: Any) -> None:  # noqa: ANN401
    """Store XCom values."""
    self.xcom[key] = value

  def xcom_pull(self, *, task_ids: str, key: str) -> Any:  # noqa: ANN401
    """Return stored XCom values."""
    return self.xcom.get(key)


class DummyDagRun:
  """Minimal dag run stub for runtime config tests."""

  def __init__(self, conf: dict[str, Any] | None = None) -> None:  # noqa: ANN401
    """Initialize with optional config."""
    self.conf = conf or {}


class DummyDAG:
  """Minimal DAG stub for module import."""

  def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
    """Initialize with keyword arguments."""
    self.kwargs = kwargs

  def __enter__(self) -> "DummyDAG":
    """Enter context manager."""
    return self

  def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:  # noqa: ANN401
    """Exit context manager."""
    return False


class DummyPythonOperator:
  """Minimal PythonOperator stub for module import."""

  def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
    """Initialize with arbitrary args and kwargs."""
    self.task_id = kwargs.get("task_id", "")

  def __rshift__(self, other: Any) -> Any:  # noqa: ANN401
    """Support >> operator for chaining."""
    return other

  def __rrshift__(self, other: Any) -> "DummyPythonOperator":  # noqa: ANN401
    """Support reverse >> operator for list chaining."""
    return self


class DummyTriggerRule:
  """Minimal TriggerRule stub for module import."""

  ALL_DONE = "all_done"


class DummyAirflowFailError(Exception):
  """Minimal AirflowFailException stub."""


def _install_airflow_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
  """Install airflow module stubs required for DAG imports."""
  airflow_mod = types.ModuleType("airflow")
  airflow_mod.DAG = DummyDAG

  exceptions_mod = types.ModuleType("airflow.exceptions")
  exceptions_mod.AirflowFailException = DummyAirflowFailError

  operators_mod = types.ModuleType("airflow.operators")
  python_mod = types.ModuleType("airflow.operators.python")
  python_mod.PythonOperator = DummyPythonOperator

  utils_mod = types.ModuleType("airflow.utils")
  trigger_mod = types.ModuleType("airflow.utils.trigger_rule")
  trigger_mod.TriggerRule = DummyTriggerRule

  email_mod = types.ModuleType("airflow.utils.email")
  email_mod.send_email = lambda **_: None

  monkeypatch.setitem(sys.modules, "airflow", airflow_mod)
  monkeypatch.setitem(sys.modules, "airflow.exceptions", exceptions_mod)
  monkeypatch.setitem(sys.modules, "airflow.operators", operators_mod)
  monkeypatch.setitem(sys.modules, "airflow.operators.python", python_mod)
  monkeypatch.setitem(sys.modules, "airflow.utils", utils_mod)
  monkeypatch.setitem(sys.modules, "airflow.utils.trigger_rule", trigger_mod)
  monkeypatch.setitem(sys.modules, "airflow.utils.email", email_mod)


def _import_dag_module(monkeypatch: pytest.MonkeyPatch, name: str) -> types.ModuleType:
  """Import a DAG module by name from the dags directory."""
  monkeypatch.syspath_prepend(str(DAGS_DIR))
  sys.modules.pop(name, None)
  return importlib.import_module(name)


class TestResumeIngestDag:
  """Tests for resume_ingest runtime helpers."""

  def test_validate_runtime_config_defaults(
    self, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Defaults to empty resumes list and pushes runtime config."""
    _install_airflow_stubs(monkeypatch)
    module = _import_dag_module(monkeypatch, "resume_ingest")

    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    task_instance = DummyTaskInstance()
    context = {"dag_run": DummyDagRun({}), "task_instance": task_instance}

    runtime = module.validate_runtime_config(**context)

    assert runtime["dsn"] == "postgresql://test"
    assert runtime["resumes"] == []
    assert task_instance.xcom["runtime"] == runtime

  def test_validate_runtime_config_rejects_invalid_resumes(
    self, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Rejects non-list resume payloads."""
    _install_airflow_stubs(monkeypatch)
    module = _import_dag_module(monkeypatch, "resume_ingest")

    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    task_instance = DummyTaskInstance()
    context = {
      "dag_run": DummyDagRun({"resumes": "bad"}),
      "task_instance": task_instance,
    }

    with pytest.raises(DummyAirflowFailError):
      module.validate_runtime_config(**context)

  def test_ingest_resumes_from_conf_processes_valid_resume(
    self, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Processes only valid resume entries."""
    _install_airflow_stubs(monkeypatch)
    module = _import_dag_module(monkeypatch, "resume_ingest")

    processed_profiles: list[dict[str, Any]] = []

    class DummyManager:
      """Stubbed cold-start manager."""

      def process_resume_file(
        self, file_path: str, *, github_username: str, full_name: str | None
      ) -> dict[str, Any]:
        return {
          "file": file_path,
          "github_username": github_username,
          "full_name": full_name,
        }

      def save_profile(self, profile: dict[str, Any]) -> None:
        processed_profiles.append(profile)

    monkeypatch.setattr(module, "ColdStartManager", lambda *, dsn: DummyManager())

    resume_payload = {
      "filename": "resume.pdf",
      "content_base64": "UERG",
      "github_username": "octocat",
      "full_name": "Octo Cat",
    }

    task_instance = DummyTaskInstance()
    task_instance.xcom["runtime"] = {
      "dsn": "postgresql://test",
      "resumes": [resume_payload, {"bad": "entry"}],
    }

    context = {"task_instance": task_instance}

    result = module.ingest_resumes_from_conf(**context)

    assert result["resumes_processed"] == 1
    assert len(processed_profiles) == 1
    assert processed_profiles[0]["github_username"] == "octocat"


class TestTicketEtlDag:
  """Tests for ticket_etl runtime helpers."""

  def test_validate_runtime_config_parses_limit(
    self, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Parses string limit_per_state and returns output directory."""
    _install_airflow_stubs(monkeypatch)
    module = _import_dag_module(monkeypatch, "ticket_etl")

    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    task_instance = DummyTaskInstance()
    context = {
      "dag_run": DummyDagRun({"limit_per_state": "150"}),
      "task_instance": task_instance,
    }

    runtime = module.validate_runtime_config(**context)

    assert runtime["limit_per_state"] == 150
    output_dir = Path(runtime["output_dir"])
    assert output_dir.name.startswith("github_issues-")
    assert output_dir.exists()
    assert task_instance.xcom["runtime"] == runtime

  def test_validate_runtime_config_rejects_bad_limit(
    self, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Raises AirflowFailException on invalid limit_per_state."""
    _install_airflow_stubs(monkeypatch)
    module = _import_dag_module(monkeypatch, "ticket_etl")

    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    task_instance = DummyTaskInstance()
    context = {
      "dag_run": DummyDagRun({"limit_per_state": "bad"}),
      "task_instance": task_instance,
    }

    with pytest.raises(DummyAirflowFailError):
      module.validate_runtime_config(**context)
