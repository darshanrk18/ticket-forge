import pandas as pd

SENIORITY_MAP = {
  "intern": 0,
  "junior": 1,
  "mid": 2,
  "senior": 3,
  "staff": 4,
  "principal": 5,
}


def enrich_engineer_features(df: pd.DataFrame) -> pd.DataFrame:
  """Add engineer-level features.

  Adds seniority_enum and historical_avg_completion_hours.
  """
  # Seniority handling
  if "seniority" in df.columns:
    df["seniority_enum"] = (
      df["seniority"].astype(str).str.lower().map(SENIORITY_MAP).fillna(2).astype(int)
    )
  else:
    df["seniority_enum"] = 2  # default = mid

  # Historical completion speed
  if "assignee" in df.columns and "completion_hours_business" in df.columns:
    df["historical_avg_completion_hours"] = df.groupby("assignee")[
      "completion_hours_business"
    ].transform("mean")
  else:
    df["historical_avg_completion_hours"] = None

  return df
