"""Temporal feature computation for tickets."""

import pandas as pd


def compute_business_completion_hours(
  created_at: str | None,
  assigned_at: str | None,
  closed_at: str | None,
) -> float | None:
  """Compute completion time in business hours.

  Uses assigned_at as start time when available, falls back to created_at.

  Args:
      created_at: ISO datetime string when ticket was created
      assigned_at: ISO datetime string when ticket was assigned (optional)
      closed_at: ISO datetime string when ticket was closed

  Returns:
      Business hours or None if closed_at is missing or result is negative
      (which indicates a data quality issue where closed_at is earlier than
      the start time, e.g. tickets closed and reopened or timestamp errors).
  """
  if closed_at is None or pd.isna(closed_at):
    return None

  # Determine start time: prefer assigned_at, fallback to created_at
  start_time = assigned_at if assigned_at and not pd.isna(assigned_at) else created_at

  if start_time is None or pd.isna(start_time):
    return None

  try:
    start = pd.to_datetime(start_time)
    end = pd.to_datetime(closed_at)
    total_hours = (end - start).total_seconds() / 3600

    # Return None for negative durations — indicates a data quality issue
    # where closed_at is earlier than start time (e.g. tickets that were
    # closed and reopened, or timestamp inconsistencies in the GitHub API).
    if total_hours < 0:
      return None

    # Approximate business hours (exclude weekends: ~5/7 of total time)
    business_hours = total_hours * (5 / 7)
    return round(business_hours, 2)
  except (ValueError, TypeError):
    return None
