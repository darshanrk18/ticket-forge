"""Tests for shared configuration and cache utilities."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from shared.cache import JoblibSaver, JsonSaver, fs_cache
from shared.configuration import Paths, getenv, getenv_or


class TestPaths:
  """Tests for Paths class."""

  def test_repo_root_exists(self) -> None:
    """Paths.repo_root is an existing directory."""
    assert Paths.repo_root.exists()
    assert Paths.repo_root.is_dir()

  def test_data_root_under_repo_root(self) -> None:
    """Paths.data_root is under repo_root."""
    assert Paths.data_root.parent == Paths.repo_root

  def test_models_root_under_repo_root(self) -> None:
    """Paths.models_root is under repo_root."""
    assert Paths.models_root.parent == Paths.repo_root


class TestGetenv:
  """Tests for getenv function."""

  def test_getenv_returns_value_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Getenv returns value when env var is set."""
    monkeypatch.setenv("TEST_VAR", "test_value")
    result = getenv("TEST_VAR")
    assert result == "test_value"

  def test_getenv_raises_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Getenv raises RuntimeError when env var is missing."""
    monkeypatch.delenv("MISSING_VAR", raising=False)
    with pytest.raises(RuntimeError, match="missing MISSING_VAR"):
      getenv("MISSING_VAR")


class TestGetenvOr:
  """Tests for getenv_or function."""

  def test_getenv_or_returns_value_when_set(
    self, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """getenv_or returns value when env var is set."""
    monkeypatch.setenv("TEST_VAR", "actual_value")
    result = getenv_or("TEST_VAR", "default")
    assert result == "actual_value"

  def test_getenv_or_returns_default_when_missing(
    self, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """getenv_or returns default when env var is missing."""
    monkeypatch.delenv("MISSING_VAR", raising=False)
    result = getenv_or("MISSING_VAR", "default_value")
    assert result == "default_value"

  def test_getenv_or_returns_none_when_no_default(
    self, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """getenv_or returns None when no default provided and var missing."""
    monkeypatch.delenv("MISSING_VAR", raising=False)
    result = getenv_or("MISSING_VAR")
    assert result is None


class TestJoblibSaver:
  """Tests for JoblibSaver."""

  def test_joblib_saver_dump_and_load(self) -> None:
    """JoblibSaver dumps and loads objects."""
    saver = JoblibSaver()

    with tempfile.TemporaryDirectory() as tmpdir:
      save_path = Path(tmpdir) / "test.pkl"

      # Dump
      data = {"key": "value", "list": [1, 2, 3]}
      saver.dump(data, save_path)

      assert save_path.exists()

      # Load
      loaded = saver.load(save_path)
      assert loaded == data


class TestJsonSaver:
  """Tests for JsonSaver."""

  def test_json_saver_dump_and_load(self) -> None:
    """JsonSaver dumps and loads JSON-serializable objects."""
    saver = JsonSaver()

    with tempfile.TemporaryDirectory() as tmpdir:
      save_path = Path(tmpdir) / "test.json"

      # Dump
      data = {"key": "value", "list": [1, 2, 3], "nested": {"x": 10}}
      saver.dump(data, save_path)

      assert save_path.exists()

      # Load
      loaded = saver.load(save_path)
      assert loaded == data

  def test_json_saver_handles_complex_types(self) -> None:
    """JsonSaver handles dict and list types."""
    saver = JsonSaver()

    with tempfile.TemporaryDirectory() as tmpdir:
      save_path = Path(tmpdir) / "test.json"

      data = {"array": [1, 2, 3], "obj": {"nested": True}}
      saver.dump(data, save_path)
      loaded = saver.load(save_path)

      assert isinstance(loaded, dict)
      assert isinstance(loaded["array"], list)


class TestFsCache:
  """Tests for fs_cache decorator."""

  def test_fs_cache_caches_function_result(self) -> None:
    """fs_cache decorator caches function result to disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
      cache_path = Path(tmpdir) / "cache"

      call_count = 0

      @fs_cache(cache_path)
      def expensive_function(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * 2

      # First call
      result1 = expensive_function(5)
      assert result1 == 10
      assert call_count == 1

      # Second call (should use cache)
      result2 = expensive_function(5)
      assert result2 == 10
      assert call_count == 1  # Not incremented, used cache

  def test_fs_cache_different_arguments(self) -> None:
    """fs_cache creates separate cache entries for different arguments."""
    with tempfile.TemporaryDirectory() as tmpdir:
      cache_path_2 = Path(tmpdir) / "cache_2"
      cache_path_3 = Path(tmpdir) / "cache_3"

      call_count = 0

      def make_cached_func(path: Path):
        @fs_cache(path)
        def func(x: int) -> int:
          nonlocal call_count
          call_count += 1
          return x * 3

        return func

      func_2 = make_cached_func(cache_path_2)
      func_3 = make_cached_func(cache_path_3)

      # Different cache paths for different arguments
      result1 = func_2(2)
      result2 = func_3(3)

      assert result1 == 6
      assert result2 == 9
      # Each should compute (different cache paths)
      assert call_count == 2

  def test_fs_cache_with_json_saver(self) -> None:
    """fs_cache can use JsonSaver for serialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
      cache_path = Path(tmpdir) / "cache"
      saver = JsonSaver()

      @fs_cache(cache_path, saver=saver)
      def json_function(x: str) -> dict:
        return {"input": x, "length": len(x)}

      result1 = json_function("hello")
      result2 = json_function("hello")

      assert result1 == {"input": "hello", "length": 5}
      assert result2 == result1
