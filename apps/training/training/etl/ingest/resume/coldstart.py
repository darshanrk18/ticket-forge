"""Cold-start profile initializer from resumes and tickets.

This module builds an initial engineer profile from a resume by:
- extracting text (OCR for PDF),
- normalizing text (remove PII),
- extracting skill keywords using `ml_core.keywords`,
- generating an embedding using `ml_core.embeddings`,
- persisting the profile to a Postgres DB with pgvector.

It also supports creating stub profiles for engineers discovered
through ticket assignee fields (zero vector + empty keywords).  Stub
profiles have a NULL ``resume_base_vector``; a subsequent resume
ingest will enrich them.

Requires a running Postgres instance with the pgvector extension and
the schema from `scripts/postgres/init/02_schema.sql`` applied.
"""

import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import psycopg2
from ml_core.embeddings import get_embedding_service
from ml_core.keywords import get_keyword_extractor
from ml_core.profiles.updater import ProfileUpdater
from psycopg2.extras import RealDictCursor
from shared import get_logger
from training.etl.ingest.resume.resume_extract import ResumeExtractor
from training.etl.ingest.resume.resume_normalize import ResumeNormalizer

logger = get_logger(__name__)

# Must match the vector(384) dimension in 02_schema.sql
EMBEDDING_DIM = 384

# Cosine-distance threshold (pgvector ``<=>``) below which two vectors
# are considered identical.  Prevents pointless writes when the same
# resume is ingested twice.
SIMILARITY_THRESHOLD = 0.01


@dataclass
class TicketUser:
  """Minimal user record extracted from a ticket assignee field."""

  github_username: str
  full_name: Optional[str] = None


@dataclass
class EngineerProfile:
  """Represents an engineer's cold-start profile derived from a resume."""

  engineer_id: str
  github_username: Optional[str]
  full_name: Optional[str]
  embedding: Optional[List[float]]
  keywords: List[str]
  created_at: str


class ColdStartManager:
  """Manages cold-start profile creation from resumes and persistence to Postgres."""

  def __init__(
    self,
    dsn: Optional[str] = None,
    embedding_model: str = "all-MiniLM-L6-v2",
  ) -> None:
    """Initialize the manager with a Postgres DSN and embedding config."""
    self.dsn = dsn or os.environ.get("DATABASE_URL")
    if not self.dsn:
      msg = "No Postgres DSN provided. Pass `dsn` or set the DATABASE_URL env var."
      raise RuntimeError(msg)

    self.extractor = ResumeExtractor()
    self.normalizer = ResumeNormalizer()
    self.keyword_extractor = get_keyword_extractor()
    self.embed_service = get_embedding_service(model_name=embedding_model)
    self._updater = ProfileUpdater()

  # ------------------------------------------------------------------ #
  #  Resume processing
  # ------------------------------------------------------------------ #

  def process_resume_file(
    self,
    file_path: str,
    github_username: Optional[str] = None,
    full_name: Optional[str] = None,
  ) -> EngineerProfile:
    """Extract, normalize, and embed a single resume into an EngineerProfile."""
    extracted = self.extractor.extract(str(file_path))
    text = (
      extracted if isinstance(extracted, str) else getattr(extracted, "raw_content", "")
    )

    normalized_text, _ = self.normalizer.normalize(text)
    keywords = self.keyword_extractor.extract(normalized_text)
    emb = self.embed_service.embed_text(normalized_text)

    return EngineerProfile(
      engineer_id=(getattr(extracted, "engineer_id", None) or Path(file_path).stem),
      github_username=github_username,
      full_name=full_name or github_username or Path(file_path).stem,
      embedding=emb.tolist() if hasattr(emb, "tolist") else list(map(float, emb)),
      keywords=keywords,
      created_at=datetime.now(tz=UTC).isoformat(),
    )

  def process_directory(
    self,
    resume_dir: str,
    username_map: Optional[Dict[str, str]] = None,
  ) -> List[EngineerProfile]:
    """Process all resumes in a directory.

    `username_map` is an optional mapping from filename (without suffix)
    to github username.
    """
    dir_path = Path(resume_dir)
    profiles: List[EngineerProfile] = []

    files = [p for p in dir_path.iterdir() if p.is_file()]
    for f in files:
      gh_user = None
      key = f.stem
      if username_map and key in username_map:
        gh_user = username_map[key]
      try:
        p = self.process_resume_file(str(f), github_username=gh_user)
        profiles.append(p)
      except Exception:
        continue

    return profiles

  # ------------------------------------------------------------------ #
  #  Ticket-based user creation
  # ------------------------------------------------------------------ #

  @staticmethod
  def profiles_from_tickets(
    ticket_users: List[TicketUser],
  ) -> List[EngineerProfile]:
    """Create stub profiles for users discovered via ticket assignees.

    Users found only through tickets have no resume and no embedding,
    so ``embedding`` is set to None.  Both ``resume_base_vector`` and
    ``profile_vector`` will be NULL in the database, signaling that they
    are stubs awaiting enrichment from a real resume.
    """
    profiles: List[EngineerProfile] = []
    for tu in ticket_users:
      profiles.append(
        EngineerProfile(
          engineer_id=tu.github_username,
          github_username=tu.github_username,
          full_name=tu.full_name or tu.github_username,
          embedding=None,
          keywords=[],
          created_at=datetime.now(tz=UTC).isoformat(),
        )
      )
    return profiles

  def merge_user_sources(
    self,
    resume_profiles: List[EngineerProfile],
    ticket_users: List[TicketUser],
  ) -> List[EngineerProfile]:
    """Combine users from resumes and ticket assignees into one list.

    If a github_username appears in both sources the resume profile
    wins (it carries richer data).  Ticket-only users get zero-vector
    stub profiles.
    """
    seen_usernames: set[str] = set()
    merged: List[EngineerProfile] = []

    for rp in resume_profiles:
      if rp.github_username:
        seen_usernames.add(rp.github_username)
      merged.append(rp)

    # Only create stubs for ticket users not already covered by resumes
    ticket_only = [
      tu for tu in ticket_users if tu.github_username not in seen_usernames
    ]
    merged.extend(self.profiles_from_tickets(ticket_only))
    return merged

  # ------------------------------------------------------------------ #
  #  Postgres persistence
  # ------------------------------------------------------------------ #

  @staticmethod
  def _ensure_row(result: Optional[dict]) -> dict:
    """Guarantee a RETURNING row was produced."""
    if result is None:
      msg = "Expected RETURNING to produce a row"
      raise RuntimeError(msg)
    return result

  def _get_connection(self) -> psycopg2.extensions.connection:
    return psycopg2.connect(self.dsn)

  def save_profile(self, profile: EngineerProfile) -> dict:
    """Save a single profile. Returns member_id and action."""
    return self._upsert_profiles([profile])[0]

  def save_profiles(self, profiles: Iterable[EngineerProfile]) -> List[dict]:
    """Save multiple profiles into the Postgres `users` table."""
    return self._upsert_profiles(list(profiles))

  # ------------------------------------------------------------------ #
  #  Upsert strategies — each method performs a single SQL statement
  #  and returns ``{"member_id": …, "action": …}``.
  # ------------------------------------------------------------------ #

  def _lookup_user(
    self,
    cur: RealDictCursor,
    github_username: str,
    vec_text: str,
  ) -> Optional[dict]:
    """Find an existing user by github_username.

    Returns a dict with ``member_id``, ``is_stub`` (bool), and
    ``cosine_dist`` (float or None when the row is a stub).
    """
    cur.execute(
      "SELECT member_id, "
      "       (resume_base_vector IS NULL) AS is_stub, "
      "       CASE "
      "           WHEN resume_base_vector IS NULL THEN NULL "
      "           ELSE (resume_base_vector <=> %s::vector) "
      "       END AS cosine_dist "
      "FROM users WHERE github_username = %s",
      (vec_text, github_username),
    )
    return cur.fetchone()

  def _enrich_stub(
    self,
    cur: RealDictCursor,
    profile: EngineerProfile,
    vec_text: str,
    keywords_text: str,
    member_id: int,
  ) -> dict:
    """Replace a stub profile with real resume data.

    The stub's zero-vector is overwritten with the resume embedding and
    ``resume_base_vector`` is set (making it non-NULL).
    """
    cur.execute(
      """
      UPDATE users SET
        github_username    = COALESCE(%s, github_username),
        full_name          = COALESCE(%s, full_name),
        resume_base_vector = %s::vector,
        profile_vector     = %s::vector,
        skill_keywords     = to_tsvector('english', %s),
        updated_at         = now()
      WHERE member_id = %s
      RETURNING member_id
      """,
      (
        profile.github_username,
        profile.full_name,
        vec_text,
        vec_text,
        keywords_text,
        member_id,
      ),
    )
    result = self._ensure_row(cur.fetchone())
    return {"member_id": str(result["member_id"]), "action": "enriched"}

  def _skip_duplicate(
    self,
    cur: RealDictCursor,
    profile: EngineerProfile,
    member_id: int,
  ) -> dict:
    """Refresh metadata only — the embedding is close enough to skip.

    Called when the incoming resume vector has a cosine distance below
    ``SIMILARITY_THRESHOLD`` to the stored ``resume_base_vector``.
    """
    cur.execute(
      """
      UPDATE users SET
        github_username = COALESCE(%s, github_username),
        full_name       = COALESCE(%s, full_name),
        updated_at      = now()
      WHERE member_id = %s
      RETURNING member_id
      """,
      (
        profile.github_username,
        profile.full_name,
        member_id,
      ),
    )
    result = self._ensure_row(cur.fetchone())
    return {"member_id": str(result["member_id"]), "action": "skipped"}

  def _decay_blend(
    self,
    cur: RealDictCursor,
    profile: EngineerProfile,
    vec_text: str,
    keywords_text: str,
    member_id: int,
  ) -> dict:
    """Apply Experience Decay blend to an existing profile.

    ``profile_vector = alpha * profile_vector + (1 - alpha) * incoming``

    Uses the same formula as
    ``ml_core.profiles.updater.ProfileUpdater.update_on_ticket_completion``.

    Blending uses PostgreSQL array_fill to create scalar vectors (all elements
    set to alpha or 1-alpha) then multiplies element-wise with the profile.
    """
    alpha = self._updater.alpha
    one_minus_alpha = 1.0 - alpha
    cur.execute(
      """
      UPDATE users SET
        github_username    = COALESCE(%s, github_username),
        full_name          = COALESCE(%s, full_name),
        resume_base_vector = %s::vector,
        profile_vector     =
          (array_fill(%s::real, ARRAY[384])::vector * profile_vector +
           array_fill(%s::real, ARRAY[384])::vector * %s::vector),
        skill_keywords     =
          skill_keywords || to_tsvector('english', %s),
        updated_at         = now()
      WHERE member_id = %s
      RETURNING member_id
      """,
      (
        profile.github_username,
        profile.full_name,
        vec_text,
        alpha,
        one_minus_alpha,
        vec_text,
        keywords_text,
        member_id,
      ),
    )
    result = self._ensure_row(cur.fetchone())
    return {"member_id": str(result["member_id"]), "action": "updated"}

  def _insert_new(
    self,
    cur: RealDictCursor,
    profile: EngineerProfile,
    vec_text: str,
    keywords_text: str,
  ) -> dict:
    """Insert a brand-new user row.

    Stubs from tickets have ``embedding=None`` and get NULL for both
    ``resume_base_vector`` and ``profile_vector``. Real resume profiles
    store the embedding in both fields.
    """
    if profile.embedding is None:
      # this is the "stub"
      pass

    # Real resume profile: store embedding in both fields
    cur.execute(
      """
      INSERT INTO users
        (github_username, full_name,
          resume_base_vector, profile_vector,
          skill_keywords)
      VALUES
        (%s, %s, %s::vector, %s::vector,
          to_tsvector('english', %s))
      RETURNING member_id
      """,
      (
        profile.github_username,
        profile.full_name,
        None if profile.embedding is None else vec_text,
        vec_text,
        keywords_text,
      ),
    )
    result = self._ensure_row(cur.fetchone())
    return {"member_id": str(result["member_id"]), "action": "created"}

  # ------------------------------------------------------------------ #
  #  Orchestrator
  # ------------------------------------------------------------------ #

  @staticmethod
  def _is_zero_vector_stub(embedding: Optional[List[float]]) -> bool:
    """Check if a profile's embedding is None (ticket-sourced stub)."""
    return embedding is None

  def _upsert_profiles(self, profiles: List[EngineerProfile]) -> List[dict]:
    """Upsert profiles using github_username as the lookup key.

    Delegates to one of four strategy methods depending on the state of
    the existing row (or lack thereof):

    1. **Enrichment** (``_enrich_stub``) – row is a stub
       (``resume_base_vector IS NULL``) and the incoming profile has a
       real embedding.
    2. **Skip** (``_skip_duplicate``) – incoming embedding is nearly
       identical to the stored vector (cosine distance <
       ``SIMILARITY_THRESHOLD``).
    3. **Decay blend** (``_decay_blend``) – alpha-weighted moving
       average, same formula as ``ProfileUpdater``.
    4. **Insert** (``_insert_new``) – no existing row.

    Note: Stub profiles created from tickets (zero embeddings) never
    trigger decay blend, only insert or skip.
    """
    conn = self._get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    results: List[dict] = []

    try:
      for p in profiles:
        # Format vector text only for non-None embeddings
        vec_text = (
          "["
          + ",".join(map(str, p.embedding if p.embedding is not None else [0.0] * 384))
          + "]"
        )
        keywords_text = " ".join(p.keywords) if p.keywords else ""

        assert p.github_username, (
          "we need this to be true since full name => collision risk"
        )

        # Zero-vector stubs from tickets only insert or skip, never blend
        is_ticket_stub = self._is_zero_vector_stub(p.embedding)

        # Only lookup if not a stub (stubs have no vector to search by)
        if not is_ticket_stub:
          assert vec_text is not None, "vec_text must be set for non-stub profiles"
          row = self._lookup_user(cur, p.github_username, vec_text)
        else:
          # For stubs, just check if user exists by username
          cur.execute(
            "SELECT member_id, (resume_base_vector IS NULL) AS is_stub "
            "FROM users WHERE github_username = %s",
            (p.github_username,),
          )
          row = cur.fetchone()

        if row is None:
          results.append(self._insert_new(cur, p, vec_text, keywords_text))
          continue

        # If this is a ticket stub, skip existing user (don't enrich or blend)
        if is_ticket_stub:
          results.append(self._skip_duplicate(cur, p, row["member_id"]))
          continue

        is_same_resume = (
          row["cosine_dist"] is not None
          and float(row["cosine_dist"]) < SIMILARITY_THRESHOLD
        )

        if bool(row["is_stub"]) or not is_same_resume:
          assert vec_text is not None, "vec_text must be set for decay blend"
          results.append(
            self._decay_blend(cur, p, vec_text, keywords_text, row["member_id"])
          )
        else:
          results.append(self._skip_duplicate(cur, p, row["member_id"]))

      conn.commit()
    except Exception:
      conn.rollback()
      raise
    finally:
      cur.close()
      conn.close()

    return results


# ---------------------------------------------------------------------- #
#  ETL helper: create default profiles from scraped tickets
# ---------------------------------------------------------------------- #
def _is_falsy_or_empty(maybe_str: str | None) -> bool:
  """Helper to determine if a variable is a either fasly or an empty string.

  Expects the variable to be a string if it is not falsy.
  """
  if (
    not maybe_str
    or maybe_str is None
    or (type(maybe_str) is float and math.isnan(maybe_str))
  ):
    return True

  if type(maybe_str) is not str:
    logger.warning(f"unexpected type {maybe_str}! treating as falseish")
    return True

  return maybe_str.strip() == ""


def ensure_profiles_for_tickets(
  tickets: List[dict],
  dsn: Optional[str] = None,
  assignee_key: str = "assignee",
) -> List[dict]:
  """Create default (zero-vector) profiles for every unique assignee in *tickets*.

  This is meant to be called from the ETL pipeline after scraping GitHub
  issues.  Each ticket dict is expected to have at least an ``assignee``
  field (configurable via *assignee_key*) containing a GitHub username.

  * If a user already exists in the DB the row is left untouched (the
    stub has ``resume_base_vector IS NULL``, so a later resume ingest
    will fully enrich it).
  * If a user does not exist a new row is inserted with a zero
    ``profile_vector``, ``NULL`` ``resume_base_vector``, and empty
    keywords.

  Returns the list of upsert result dicts (``member_id`` + ``action``).
  """
  # Deduplicate assignees
  seen: set[str] = set()
  ticket_users: List[TicketUser] = []
  for t in tickets:
    username = t.get(assignee_key)
    if _is_falsy_or_empty(username):
      continue
    assert type(username) is str
    if username not in seen:
      seen.add(username)
      ticket_users.append(TicketUser(github_username=username))

  if not ticket_users:
    return []

  profiles = ColdStartManager.profiles_from_tickets(ticket_users)
  mgr = ColdStartManager(dsn=dsn)
  return mgr.save_profiles(profiles)


# ---------------------------------------------------------------------- #
#  Convenience runner
# ---------------------------------------------------------------------- #


def run_coldstart(resume_dir: str, dsn: Optional[str] = None) -> None:
  """Process all resumes in a directory and save profiles to Postgres."""
  mgr = ColdStartManager(dsn=dsn)
  profiles = mgr.process_directory(resume_dir)
  results = mgr.save_profiles(profiles)
  print(f"Saved {len(results)} profile(s) to Postgres.")
  for r in results:
    print(f"  {r['member_id']} → {r['action']}")


if __name__ == "__main__":
  import argparse

  parser = argparse.ArgumentParser(
    description="Cold-start engineer profiles from resumes into Postgres"
  )
  parser.add_argument("resume_dir", help="Directory with resume files")
  parser.add_argument(
    "--dsn",
    default=None,
    help="Postgres DSN (defaults to DATABASE_URL env var)",
  )

  args = parser.parse_args()
  run_coldstart(args.resume_dir, dsn=args.dsn)
