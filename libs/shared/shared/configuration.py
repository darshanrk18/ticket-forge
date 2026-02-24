import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

RANDOM_SEED = 42

TRAIN_USE_DUMMY_DATA = True

Splits_t = Literal["train", "test", "validation"]
SPLITS: list[Splits_t] = ["train", "test", "validation"]


class Paths:
  """Relevant paths in this project."""

  repo_root = Path(__file__).parent.parent.parent.parent
  data_root = repo_root / "data"
  models_root = repo_root / "models"


def getenv(key: str) -> str:
  """Gets env variable. Handles loading dotenv for you."""
  value = os.getenv(key)
  if value is None:
    msg = f"missing {key} in environment"
    raise RuntimeError(msg)
  return value


def getenv_or(key: str, default: str | None = None) -> str | None:
  """Gets env variable. Handles loading dotenv for you."""
  return os.getenv(key, default)
