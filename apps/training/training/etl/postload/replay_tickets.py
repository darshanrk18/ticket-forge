"""Replay closed tickets to build engineer profile history.

Simulates the continuous learning / upskilling of engineers by processing
closed tickets in chronological order and applying the Experience Decay
update to each assigned engineer's profile vector and skill keywords.

In a production system these updates would arrive via a queue whenever a
ticket is closed.  During the initial ETL we "replay" history instead:

1. Accept a list of ticket IDs to replay (provided by the caller).
2. Fetch those tickets and their assignments from Postgres, ordered
   by the ticket ``updated_at`` timestamp (proxy for close date).
3. For each ticket ⟶ engineer pair, apply the Experience Decay formula:
       profile_vector  ← α · profile_vector + (1 − α) · ticket_vector
       skill_keywords  ← skill_keywords ∪ ticket_keywords
       tickets_closed_count += 1
4. Commit once after all tickets have been processed.  Within a single
   Postgres transaction each UPDATE already sees the effects of prior
   UPDATEs (read-your-own-writes), so chronological fidelity is
   preserved while keeping the entire replay **atomic** — if any
   ticket fails, every change is rolled back.

Requires:
- A running Postgres instance with the ``02_schema.sql`` schema applied.
- The ``tickets``, ``assignments``, and ``users`` tables already populated
  (by the ingest stage of the ETL pipeline).

Usage::

    python -m training.etl.postload.replay_tickets \
        T-1 T-2 T-3 [--dsn DSN] [--alpha 0.95]
    python -m training.etl.postload.replay_tickets \
        --file ticket_ids.txt [--dsn DSN]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import psycopg2
from ml_core.keywords import get_keyword_extractor
from ml_core.profiles.updater import ProfileUpdater
from psycopg2.extras import RealDictCursor
from shared.logging import get_logger
from training.etl.dsn import resolve_postgres_dsn

logger = get_logger(__name__)

# Default decay weight — matches ``ml_core.profiles.updater.ProfileUpdater``
DEFAULT_ALPHA = 0.95


# ---------------------------------------------------------------------- #
#  Data containers
# ---------------------------------------------------------------------- #


@dataclass
class ClosedTicketAssignment:
  """One row from the closed-tickets-with-assignments query."""

  assignment_id: str
  ticket_id: str
  title: str
  description: str
  engineer_id: int
  github_username: str | None
  closed_at: str  # ISO timestamp (from tickets.updated_at)


# ---------------------------------------------------------------------- #
#  Core replay logic
# ---------------------------------------------------------------------- #


class TicketReplayer:
  """Replay closed tickets chronologically to update engineer profiles."""

  def __init__(
    self,
    dsn: str | None = None,
    alpha: float = DEFAULT_ALPHA,
  ) -> None:
    """Initialise the replayer.

    Args:
        dsn: Postgres connection string.  Falls back to the
            ``DATABASE_URL`` environment variable.
        alpha: Decay weight for the Experience Decay Method.
    """
    self.dsn = resolve_postgres_dsn(dsn)

    if not 0 < alpha < 1:
      msg = f"Alpha must be between 0 and 1 exclusive, got {alpha}"
      raise ValueError(msg)

    self.alpha = alpha
    self.keyword_extractor = get_keyword_extractor()
    self._updater = ProfileUpdater(alpha=alpha)

  # ------------------------------------------------------------------ #
  #  Database helpers
  # ------------------------------------------------------------------ #

  def _get_connection(self) -> psycopg2.extensions.connection:
    return psycopg2.connect(self.dsn)

  @staticmethod
  def _fetch_closed_ticket_assignments(
    cur: RealDictCursor,
    ticket_ids: list[str],
  ) -> list[ClosedTicketAssignment]:
    """Fetch the given tickets joined with their assignments, ordered by close date.

    Only tickets whose IDs appear in *ticket_ids* are returned.
    Uses ``tickets.updated_at`` as the chronological ordering key since
    that is set when the ticket transitions to *closed*.
    """
    cur.execute(
      """
      SELECT
        a.assignment_id,
        t.ticket_id,
        t.title,
        t.description,
        a.engineer_id,
        u.github_username,
        t.updated_at AS closed_at
      FROM tickets t
        JOIN assignments a ON a.ticket_id = t.ticket_id
        JOIN users u       ON u.member_id = a.engineer_id
      WHERE t.ticket_id = ANY(%s)
        AND t.status = 'closed'
        AND a.replayed_at IS NULL
      ORDER BY t.updated_at ASC
      """,
      (ticket_ids,),
    )
    rows = cur.fetchall()
    return [
      ClosedTicketAssignment(
        assignment_id=str(r["assignment_id"]),
        ticket_id=r["ticket_id"],
        title=r["title"],
        description=r["description"],
        engineer_id=r["engineer_id"],
        github_username=r["github_username"],
        closed_at=str(r["closed_at"]),
      )
      for r in rows
    ]

  def _apply_ticket_update(
    self,
    cur: RealDictCursor,
    assignment: ClosedTicketAssignment,
  ) -> None:
    """Apply the Experience Decay update for one ticket→engineer pair.

    Delegates to :meth:`ProfileUpdater.build_profile_update_query` so that
    the decay formula is defined in one place.  The update executes entirely
    in SQL — no vector round-trip through Python.
    """
    # Extract keywords from ticket text
    ticket_text = f"{assignment.title} {assignment.description or ''}"
    keywords = self.keyword_extractor.extract(ticket_text)
    keywords_text = " ".join(keywords) if keywords else ""

    sql, params = self._updater.build_profile_update_query(
      ticket_id=assignment.ticket_id,
      engineer_id=assignment.engineer_id,
      keywords_text=keywords_text,
    )
    cur.execute(sql, params)

  @staticmethod
  def _mark_assignment_replayed(
    cur: RealDictCursor,
    assignment: ClosedTicketAssignment,
  ) -> None:
    """Mark a replayed assignment so future DAG runs skip it."""
    cur.execute(
      """
      UPDATE assignments
      SET replayed_at = now()
      WHERE assignment_id = %s
      """,
      (assignment.assignment_id,),
    )

  # ------------------------------------------------------------------ #
  #  Public API
  # ------------------------------------------------------------------ #

  def replay(self, ticket_ids: list[str]) -> int:
    """Replay the given tickets and return the number of updates applied.

    Args:
        ticket_ids: Ticket IDs to replay.  They will be fetched from the
                    database, joined with their assignments, and processed
                    in chronological order.

    All updates run inside a single transaction so the replay is
    **atomic**: if any ticket fails, every change is rolled back.
    Within the transaction each UPDATE still sees prior UPDATEs
    (Postgres read-your-own-writes), preserving chronological fidelity.
    """
    if not ticket_ids:
      logger.info("No ticket IDs provided — nothing to replay.")
      return 0

    conn = self._get_connection()
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
      assignments = self._fetch_closed_ticket_assignments(cur, ticket_ids)
      total = len(assignments)

      if total == 0:
        logger.info("No closed ticket assignments found — nothing to replay.")
        return 0

      logger.info(
        "Replaying %d closed ticket assignment(s) with alpha=%.4f …",
        total,
        self.alpha,
      )

      for idx, assignment in enumerate(assignments, start=1):
        self._apply_ticket_update(cur, assignment)
        self._mark_assignment_replayed(cur, assignment)

        if idx % 100 == 0 or idx == total:
          logger.info(
            "  [%d/%d] last ticket=%s  engineer=%s",
            idx,
            total,
            assignment.ticket_id,
            assignment.github_username or assignment.engineer_id,
          )

      conn.commit()
      logger.info("Replay complete. %d update(s) applied.", total)

    except Exception:
      conn.rollback()
      logger.exception("Replay failed — rolling back all updates.")
      raise
    else:
      return total
    finally:
      cur.close()
      conn.close()


# ---------------------------------------------------------------------- #
#  CLI
# ---------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> None:
  """CLI entry-point for the ticket replay post-load step."""
  parser = argparse.ArgumentParser(
    description="Replay closed tickets to build engineer profile history.",
  )
  parser.add_argument(
    "--dsn",
    default=None,
    help="Postgres DSN (defaults to DATABASE_URL env var).",
  )
  parser.add_argument(
    "--alpha",
    type=float,
    default=DEFAULT_ALPHA,
    help=f"Decay weight for the Experience Decay Method (default: {DEFAULT_ALPHA}).",
  )
  parser.add_argument(
    "ticket_ids",
    nargs="*",
    help="Ticket IDs to replay. Can also be provided via --file.",
  )
  parser.add_argument(
    "--file",
    "-f",
    default=None,
    dest="ticket_file",
    help="Path to a file containing ticket IDs (one per line).",
  )

  args = parser.parse_args(argv)

  # Collect ticket IDs from positional args and/or --file
  ids: list[str] = list(args.ticket_ids or [])
  if args.ticket_file:
    with open(args.ticket_file) as fh:
      ids.extend(line.strip() for line in fh if line.strip())

  if not ids:
    parser.error("No ticket IDs provided. Pass them as arguments or via --file.")

  replayer = TicketReplayer(dsn=args.dsn, alpha=args.alpha)
  count = replayer.replay(ids)

  if count == 0:
    print("No matching ticket assignments found — nothing to replay.")
  else:
    print(f"Replayed {count} ticket assignment(s).")


if __name__ == "__main__":
  main()
