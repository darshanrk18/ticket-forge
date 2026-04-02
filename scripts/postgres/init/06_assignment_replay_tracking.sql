-- Track whether a closed-ticket assignment has already been replayed into
-- an engineer profile so Airflow reruns do not apply the same ticket twice.

ALTER TABLE assignments
ADD COLUMN IF NOT EXISTS replayed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_assignments_replayed_at
  ON assignments(replayed_at);
