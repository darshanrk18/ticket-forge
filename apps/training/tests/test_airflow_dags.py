"""Tests for Airflow DAG source files."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DAGS_DIR = REPO_ROOT / "dags"


def _parse_module(path: Path) -> ast.Module:
  """Parse a Python file into an AST module."""
  return ast.parse(path.read_text(encoding="utf-8"))


def _find_constant_str(module: ast.Module, name: str) -> str | None:
  """Return string literal value assigned to a top-level name."""
  for node in module.body:
    if isinstance(node, ast.Assign):
      for target in node.targets:
        if isinstance(target, ast.Name) and target.id == name:
          if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
  return None


def _top_level_function_names(module: ast.Module) -> set[str]:
  """Return top-level function names from a module AST."""
  return {node.name for node in module.body if isinstance(node, ast.FunctionDef)}


def _contains_string_literal(module: ast.Module, value: str) -> bool:
  """Return whether a module contains a given string literal."""
  for node in ast.walk(module):
    if isinstance(node, ast.Constant) and node.value == value:
      return True
  return False


class TestDagFiles:
  """Validate DAG source files exist and declare expected metadata."""

  @pytest.mark.parametrize(
    ("filename", "expected_dag_id", "expected_functions"),
    [
      (
        "ticket_etl.py",
        "ticket_etl",
        {"validate_runtime_config", "run_transform", "upload_output_dir_to_gcs"},
      ),
      (
        "ticket_etl_from_file.py",
        "ticket_etl_from_file",
        {"validate_runtime_config", "run_transform", "upload_output_dir_to_gcs"},
      ),
      (
        "resume_ingest.py",
        "resume_etl",
        {"validate_runtime_config"},
      ),
    ],
  )
  def test_dag_file_contract(
    self,
    filename: str,
    expected_dag_id: str,
    expected_functions: set[str],
  ) -> None:
    """Each DAG module should define DAG_ID and expected task/factory functions."""
    path = DAGS_DIR / filename
    assert path.exists(), f"Missing DAG file: {path}"

    module = _parse_module(path)

    dag_id = _find_constant_str(module, "DAG_ID")
    assert dag_id == expected_dag_id

    function_names = _top_level_function_names(module)
    for fn in expected_functions:
      assert fn in function_names

  def test_resume_ingest_bootstraps_pipelines_workspace(self) -> None:
    """Resume ingest DAG should add the pipelines workspace to sys.path."""
    path = DAGS_DIR / "resume_ingest.py"
    module = _parse_module(path)

    assert _contains_string_literal(module, "pipelines")
