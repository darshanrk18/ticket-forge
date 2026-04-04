"""Dataset utilities for machine learning pipelines."""

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from pydantic import BaseModel
from shared.configuration import (
  RANDOM_SEED,
  TRAIN_USE_DUMMY_DATA,
  Paths,
  Splits_t,
  getenv_or,
)
from shared.logging import get_logger
from sklearn.datasets import make_classification
from sklearn.model_selection import PredefinedSplit

logger = get_logger(__name__)
# Module-level cache for loaded records
# Avoids re-reading 61k records from disk on every CV fold
_records_cache: dict[str, list] = {}


X_t = npt.NDArray[Any]
Y_t = npt.NDArray[Any]

# Split ratios for train / validation / test
_SPLIT_RATIOS: dict[str, float] = {"train": 0.7, "validation": 0.15, "test": 0.15}

# Time bucket boundaries (in business hours)
# Bucket 0: S  —  0-10 hrs  (small,  quick fix)
# Bucket 1: M  — 10-50 hrs  (medium, few days)
# Bucket 2: L  — 50-100 hrs (large,  ~2 weeks)
# Bucket 3: XL — 100-480 hrs(x-large, long haul)
# Tickets above 480 hrs (~60 working days) are dropped as abandoned/noise
TIME_BUCKETS = [0, 10, 50, 100, 480]
N_CLASSES = len(TIME_BUCKETS) - 1

_DATETIME_FMT = "%Y-%m-%dT%H:%M:%SZ"
_MAX_TTA_HOURS = 720.0  # cap time-to-assignment at 30 days
_DATASET_FILE_CANDIDATES = (
  "tickets_transformed_improved.jsonl",
  "tickets_transformed_improved.jsonl.gz",
)


def _parse_tta(created: str | None, assigned: str | None) -> float:
  """Computes time-to-assignment in hours.

  Returns 0.0 for missing, negative, or unparseable values.
  Caps at _MAX_TTA_HOURS (30 days) to avoid outlier noise.

  Args:
      created:  ISO timestamp string for ticket creation.
      assigned: ISO timestamp string for ticket assignment.

  Returns:
      Time-to-assignment in hours, clipped to [0, _MAX_TTA_HOURS].
  """
  if not created or not assigned:
    return 0.0
  if not isinstance(assigned, str) or not isinstance(created, str):
    return 0.0
  try:
    t_created = datetime.strptime(created, _DATETIME_FMT).replace(tzinfo=timezone.utc)
    t_assigned = datetime.strptime(assigned, _DATETIME_FMT).replace(tzinfo=timezone.utc)
    tta = (t_assigned - t_created).total_seconds() / 3600
    return float(max(0.0, min(tta, _MAX_TTA_HOURS)))
  except ValueError:
    return 0.0


def _find_dataset_file(directory: Path) -> Path | None:
  """Return the first supported transformed dataset file in a directory.

  Args:
      directory: Candidate pipeline output directory.

  Returns:
      Path to a supported dataset file, or None if none are present.
  """
  for filename in _DATASET_FILE_CANDIDATES:
    candidate = directory / filename
    if candidate.exists():
      return candidate
  return None


def find_latest_pipeline_output() -> Path:
  """Returns the path to the most recent timestamped pipeline output directory
  that contains a tickets_transformed_improved.jsonl[.gz] file.

  First checks the TICKET_FORGE_DATASET_ID environment variable for an explicit
  dataset override. If set, uses that dataset ID (can be either a directory name
  like 'github_issues-2026-02-24T200000Z' or an absolute path).

  If no override is set, looks for directories matching 'github_issues-*' under
  data_root, sorted lexicographically (ISO timestamps sort correctly this way),
  skipping any incomplete directories that lack the required data file. Falls
  back to the legacy 'github_issues' directory if no valid timestamped run is found.

  Returns:
      Path to the latest valid pipeline output directory.

  Raises:
      FileNotFoundError: If no valid pipeline output directory can be located.
  """
  data_root = Paths.data_root
  required_files = " or ".join(_DATASET_FILE_CANDIDATES)

  # Check for explicit dataset override via environment variable
  dataset_override = getenv_or("TICKET_FORGE_DATASET_ID")
  if dataset_override:
    override_path = Path(dataset_override)
    # If relative, resolve relative to data_root; if absolute, use as-is
    if not override_path.is_absolute():
      override_path = data_root / override_path
    if _find_dataset_file(override_path) is not None:
      logger.info(f"using dataset override: {override_path}")
      return override_path
    msg = (
      f"Dataset override {dataset_override} is not valid or missing "
      f"{required_files}. Override path resolved to: {override_path}"
    )
    raise FileNotFoundError(msg)

  # Default: find latest timestamped run
  timestamped = sorted(data_root.glob("github_issues-*"), reverse=True)
  for candidate in timestamped:
    if _find_dataset_file(candidate) is not None:
      logger.info(f"latest piece of data: {candidate}")
      return candidate
  legacy = data_root / "github_issues"
  if _find_dataset_file(legacy) is not None:
    return legacy
  msg = (
    f"No valid pipeline output found under {data_root}. "
    "Run the ticket_etl DAG or scraper first."
  )
  raise FileNotFoundError(msg)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
  """Loads a .jsonl or .jsonl.gz file into a list of dicts.

  Args:
      path: Path to the .jsonl or .jsonl.gz file.

  Returns:
      List of parsed JSON objects.

  Raises:
      FileNotFoundError: If the file does not exist.
  """
  if not path.exists():
    msg = f"Expected data file not found: {path}"
    raise FileNotFoundError(msg)
  records = []
  if path.suffix == ".gz":
    open_fn = gzip.open
  else:
    open_fn = open

  with open_fn(path, "rt", encoding="utf-8") as f:
    for line in f:
      line = line.strip()
      if line:
        records.append(json.loads(line))
  logger.info(f"loaded {len(records)}")
  return records


def _split_indices(
  n: int, split: Splits_t, seed: int = RANDOM_SEED
) -> npt.NDArray[np.intp]:
  """Returns row indices for the requested split.

  Shuffles deterministically using seed, then slices according to
  _SPLIT_RATIOS so every split sees a different, non-overlapping subset.

  Args:
      n:     Total number of records.
      split: One of 'train', 'validation', or 'test'.
      seed:  Random seed for reproducibility.

  Returns:
      Array of integer indices for the requested split.
  """
  rng = np.random.default_rng(seed=seed)
  idx = rng.permutation(n)

  train_end = int(n * _SPLIT_RATIOS["train"])
  val_end = train_end + int(n * _SPLIT_RATIOS["validation"])

  if split == "train":
    return idx[:train_end]
  if split == "validation":
    return idx[train_end:val_end]
  # test
  return idx[val_end:]


class Dataset(BaseModel):
  """Represents training dataset for ticket complexity classification.

  Loads real pipeline output from the latest timestamped run directory
  under data_root when TRAIN_USE_DUMMY_DATA is False. Falls back to
  synthetically generated data when TRAIN_USE_DUMMY_DATA is True.

  Target variable is a time bucket class (0-3) based on
  completion_hours_business:
    0: S  —  0-10 hrs  (small)
    1: M  — 10-50 hrs  (medium)
    2: L  — 50-100 hrs (large)
    3: XL — 100-480 hrs(x-large)
  """

  split: Splits_t
  subset_size: int | None = None

  # ------------------------------------------------------------------ #
  # Internal helpers                                                   #
  # ------------------------------------------------------------------ #

  def _load_records(self) -> list[dict[str, Any]]:
    """Loads and splits the balanced ticket records for this split.

    Records with missing or negative completion_hours_business are dropped
    entirely — no imputation. Long-duration tickets are retained as they
    reflect real backlog/prioritization behaviour.

    Returns:
        List of ticket dicts belonging to this split.
    """
    pipeline_dir = find_latest_pipeline_output()
    dataset_path = _find_dataset_file(pipeline_dir)
    if dataset_path is None:
      msg = (
        "Expected transformed dataset file not found in "
        f"{pipeline_dir}. Tried: {', '.join(_DATASET_FILE_CANDIDATES)}"
      )
      raise FileNotFoundError(msg)

    cache_key = str(dataset_path)
    if cache_key not in _records_cache:
      _records_cache[cache_key] = _load_jsonl(dataset_path)
    all_records = _records_cache[cache_key]

    indices = _split_indices(len(all_records), self.split)
    records = [all_records[i] for i in indices]

    n_records = len(records)

    # Drop records with missing, negative, or abandoned completion times.
    # No mean imputation — garbage records are excluded entirely.
    # Tickets above 480 hrs (~60 working days) are dropped as abandoned/noise
    # based on industry research showing legitimate tickets rarely exceed this.
    records = [
      r
      for r in records
      if r.get("completion_hours_business") is not None
      and 0 <= r["completion_hours_business"] <= 480
    ]

    if self.subset_size is not None:
      records = records[: self.subset_size]

    logger.info(
      f"loaded {len(records)}/{n_records} record(s) {self.subset_size=} {self.split=}"
    )
    return records

  # ------------------------------------------------------------------ #
  # Public loaders                                                     #
  # ------------------------------------------------------------------ #

  def load_x(self) -> X_t:
    """Loads the feature matrix X.

    Each row contains:
    - 384-dimensional embedding vector (all-MiniLM-L6-v2)
    - Engineered features: repo one-hot, label flags, comments count,
      historical avg completion, keyword count, text length, and
      time-to-assignment (proxy for ticket priority).
      Note: seniority_enum excluded — all labels are 'mid', zero variance.

    TF-IDF features have been removed to reduce overfitting risk and
    improve generalization.

    Returns:
        Float32 array of shape (n_samples, 384 + 12).
    """
    if TRAIN_USE_DUMMY_DATA:
      dataset = make_classification(
        n_samples=100,
        n_features=10,
        n_classes=N_CLASSES,
        n_informative=5,
        random_state=42,
      )
      x = dataset[0]
      if self.subset_size is not None:
        return x[: self.subset_size]  # type: ignore[return-value]
      return x  # type: ignore[return-value]

    records = self._load_records()

    # --- Embeddings (384-dim) ---
    embeddings = np.array([r["embedding"] for r in records], dtype=np.float32)

    # --- Engineered features (12-dim) ---
    repos = ["ansible/ansible", "hashicorp/terraform", "prometheus/prometheus"]
    engineered = []
    for r in records:
      repo = r.get("repo", "")
      repo_onehot = [1.0 if repo == R else 0.0 for R in repos]

      labels = r.get("labels", "") or ""
      has_bug = 1.0 if "bug" in labels else 0.0
      has_enhancement = 1.0 if "enhancement" in labels else 0.0
      has_crash = 1.0 if "crash" in labels else 0.0

      comments = float(r.get("comments_count") or 0)
      hist_avg = float(r.get("historical_avg_completion_hours") or 0)
      kw_count = float(len(r.get("keywords") or []))
      title_len = float(len(r.get("title") or ""))
      body_len = float(len(r.get("body") or ""))

      # Time-to-assignment: proxy for ticket priority.
      # Fast assignment = high urgency. Negative/missing = 0.0.
      # Capped at 720 hrs (30 days) to avoid outlier noise.
      tta = _parse_tta(r.get("created_at"), r.get("assigned_at"))

      engineered.append(
        repo_onehot
        + [
          has_bug,
          has_enhancement,
          has_crash,
          comments,
          hist_avg,
          kw_count,
          title_len,
          body_len,
          tta,
        ]
      )

    eng_arr = np.array(engineered, dtype=np.float32)

    return np.nan_to_num(np.hstack([embeddings, eng_arr]), nan=0.0)

  def load_y(self) -> Y_t:
    """Loads the target vector y as time bucket class labels.

    Converts completion_hours_business into one of 4 buckets:
      0: S  —  0-10 hrs
      1: M  — 10-50 hrs
      2: L  — 50-100 hrs
      3: XL — 100-480 hrs

    Records with missing or negative completion hours are already dropped
    in _load_records() — no imputation is applied here.

    Returns:
        Int64 array of shape (n_samples,) with class labels 0–3.
    """
    if TRAIN_USE_DUMMY_DATA:
      dataset = make_classification(
        n_samples=100,
        n_features=10,
        n_classes=N_CLASSES,
        n_informative=5,
        random_state=42,
      )
      y = dataset[1]
      if self.subset_size is not None:
        return y[: self.subset_size]  # type: ignore[return-value]
      return y  # type: ignore[return-value]

    records = self._load_records()
    raw = [r.get("completion_hours_business") for r in records]
    y = np.array(raw, dtype=np.float64)

    # Convert continuous hours to time bucket class labels
    # TIME_BUCKETS = [0, 10, 50, 100, 480]
    # Bucket 0: S (0-10), 1: M (10-50), 2: L (50-100), 3: XL (100-480)
    return np.digitize(y, TIME_BUCKETS[1:-1]).astype(np.int64)

  def load_metadata(self) -> pd.DataFrame:
    """Loads metadata for bias analysis (repo, seniority, labels, completion time).

    Returns:
        DataFrame with columns: repo, seniority, labels,
        completion_hours_business.
    """
    if TRAIN_USE_DUMMY_DATA:
      n_samples = self.subset_size if self.subset_size is not None else 100
      rng = np.random.default_rng(seed=42)
      return pd.DataFrame(
        {
          "repo": rng.choice(["terraform", "ansible", "prometheus"], size=n_samples),
          "seniority": rng.choice(["junior", "mid", "senior"], size=n_samples),
          "labels": rng.choice(
            ["bug", "enhancement", "feature", "bug,critical"],
            size=n_samples,
          ),
          "completion_hours_business": rng.uniform(1, 100, size=n_samples),
        }
      )

    records = self._load_records()
    return pd.DataFrame(
      {
        "repo": [r.get("repo", "") for r in records],
        "seniority": [r.get("seniority", "mid") for r in records],
        "labels": [r.get("labels", "") for r in records],
        "completion_hours_business": [
          r.get("completion_hours_business") for r in records
        ],
      }
    )

  def load_sample_weights(self) -> Y_t:
    """Loads per-sample weights for bias-aware training.

    Attempts to load weights from sample_weights.json in the latest
    pipeline output directory. Falls back to inverse-frequency weights
    derived from the metadata repo column if the file is missing or
    malformed.

    Returns:
        Float64 array of per-sample weights, same length as load_y().
    """
    group_col = "repo"
    meta = self.load_metadata()

    # Try loading from the latest pipeline output directory first,
    # then fall back to the legacy fixed path.
    candidates: list[Path] = []
    try:
      candidates.append(find_latest_pipeline_output() / "sample_weights.json")
    except FileNotFoundError:
      pass
    candidates.append(Paths.data_root / "github_issues" / "sample_weights.json")

    for weights_path in candidates:
      try:
        with open(weights_path) as f:
          data: dict[str, Any] = json.load(f)
        saved_col: str = data.get("group_col", group_col)
        weights_by_group: dict[str, float] = data.get("weights_by_group", {})
        if saved_col in meta.columns and weights_by_group:
          w = meta[saved_col].map(weights_by_group).fillna(1.0)  # type: ignore[arg-type]
          return w.to_numpy(dtype=np.float64)  # type: ignore[return-value]
      except (FileNotFoundError, json.JSONDecodeError):
        continue

    # Fallback: inverse-frequency weights from metadata repo column
    group_counts = meta[group_col].value_counts()
    total = len(meta)
    n_groups = len(group_counts)
    w = meta[group_col].map(lambda g: total / (n_groups * group_counts[g]))
    return w.to_numpy(dtype=np.float64)  # type: ignore[return-value]

  # ------------------------------------------------------------------ #
  # Sklearn CV helpers                                                  #
  # ------------------------------------------------------------------ #

  @staticmethod
  def as_sklearn_cv_split(
    subset_size: int | None = None,
  ) -> tuple[X_t, Y_t, PredefinedSplit]:
    """Creates a predefined sklearn cross-validation split with fixed
    training and validation partitions.

    Returns:
        Tuple of (x_combined, y_combined, cv_split).
    """
    train = Dataset(split="train", subset_size=subset_size)
    validation = Dataset(split="validation", subset_size=subset_size)

    x_train = train.load_x()
    y_train = train.load_y()
    x_val = validation.load_x()
    y_val = validation.load_y()

    x_combined = np.vstack([x_train, x_val])
    y_combined = np.hstack([y_train, y_val])

    test_fold = np.concatenate(
      [np.full(x_train.shape[0], -1), np.full(x_val.shape[0], 0)]
    )
    cv_split = PredefinedSplit(test_fold)

    return x_combined, y_combined, cv_split

  @staticmethod
  def as_sklearn_cv_split_with_weights(
    subset_size: int | None = None,
  ) -> tuple[X_t, Y_t, PredefinedSplit, Y_t]:
    """Like as_sklearn_cv_split but also returns per-sample weights.

    Returns:
        Tuple of (x_combined, y_combined, cv_split, weights_combined).
    """
    train = Dataset(split="train", subset_size=subset_size)
    validation = Dataset(split="validation", subset_size=subset_size)

    x_train, y_train = train.load_x(), train.load_y()
    w_train = train.load_sample_weights()
    x_val, y_val = validation.load_x(), validation.load_y()
    w_val = validation.load_sample_weights()

    x_combined = np.vstack([x_train, x_val])
    y_combined = np.hstack([y_train, y_val])
    w_combined = np.hstack([w_train, w_val])

    test_fold = np.concatenate(
      [np.full(x_train.shape[0], -1), np.full(x_val.shape[0], 0)]
    )
    cv_split = PredefinedSplit(test_fold)

    return x_combined, y_combined, cv_split, w_combined
