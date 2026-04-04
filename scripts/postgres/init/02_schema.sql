-- Schema for storing engineered features and embeddings (users, tickets, assignments).
-- Tabular data and vectors live in the same database.
-- Supports hybrid search: semantic (vector) + lexical (full-text).

-- Create ENUM for ticket status.
DO $$ BEGIN
  CREATE TYPE ticket_status AS ENUM ('open', 'in-progress', 'closed');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- Users: engineer profiles with dynamic profile vectors and skill keywords.
-- Profile vectors evolve as tickets are completed (moving average with decay).
CREATE TABLE IF NOT EXISTS users (
  member_id            BIGINT PRIMARY KEY DEFAULT floor(random() * 9000000000 + 1000000000)::bigint,
  github_username      TEXT UNIQUE,
  full_name            TEXT NOT NULL,
  resume_base_vector   vector(384),
  profile_vector       vector(384) NOT NULL,
  skill_keywords       tsvector NOT NULL,
  tickets_closed_count INTEGER NOT NULL DEFAULT 0,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_profile_vector ON users
  USING ivfflat (profile_vector vector_cosine_ops)
  WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_users_resume_base_vector ON users
  USING ivfflat (resume_base_vector vector_cosine_ops)
  WITH (lists = 100);

-- GIN index for full-text search on skill_keywords (hybrid search).
CREATE INDEX IF NOT EXISTS idx_users_skill_keywords ON users
  USING gin (skill_keywords);

COMMENT ON TABLE users IS 'Engineer profiles with dynamic profile vectors and skill keywords for hybrid search.';

-- Tickets: issues/tickets with semantic embeddings and metadata.
CREATE TABLE IF NOT EXISTS tickets (
  ticket_id            TEXT PRIMARY KEY,
  title                TEXT NOT NULL,
  description          TEXT NOT NULL,
  ticket_vector        vector(384) NOT NULL,
  labels               JSONB,
  status               ticket_status NOT NULL DEFAULT 'open',
  resolution_time_actual INTERVAL,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tickets_ticket_vector ON tickets
  USING ivfflat (ticket_vector vector_cosine_ops)
  WITH (lists = 100);

-- GIN index for JSONB labels (for filtering by labels).
CREATE INDEX IF NOT EXISTS idx_tickets_labels ON tickets
  USING gin (labels);

-- Full-text search indexes on title and description (hybrid search).
CREATE INDEX IF NOT EXISTS idx_tickets_title_fts ON tickets
  USING gin (to_tsvector('english', title));

CREATE INDEX IF NOT EXISTS idx_tickets_description_fts ON tickets
  USING gin (to_tsvector('english', description));

CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);

COMMENT ON TABLE tickets IS 'Ticket/issue records with semantic embeddings and metadata for hybrid matching.';

-- Assignments: tracks ticket-to-engineer assignments.
CREATE TABLE IF NOT EXISTS assignments (
  assignment_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id            TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
  engineer_id          BIGINT NOT NULL REFERENCES users(member_id) ON DELETE CASCADE,
  assigned_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  replayed_at          TIMESTAMPTZ,
  UNIQUE(ticket_id, engineer_id)
);

CREATE INDEX IF NOT EXISTS idx_assignments_ticket_id ON assignments(ticket_id);
CREATE INDEX IF NOT EXISTS idx_assignments_engineer_id ON assignments(engineer_id);
CREATE INDEX IF NOT EXISTS idx_assignments_assigned_at ON assignments(assigned_at);
CREATE INDEX IF NOT EXISTS idx_assignments_replayed_at ON assignments(replayed_at);

COMMENT ON TABLE assignments IS 'Tracks ticket assignments to engineers for profile updates and learning.';
