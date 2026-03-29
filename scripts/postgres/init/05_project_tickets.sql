-- Project tickets for TicketForge board system.
-- Runs after 04_projects.sql.
-- Adds project_tickets and ticket key counters.

-- ------------------------------------------------------------------ --
--  ENUM: ticket priority
-- ------------------------------------------------------------------ --

DO $$ BEGIN
    CREATE TYPE ticket_priority AS ENUM ('low', 'medium', 'high', 'critical');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ------------------------------------------------------------------ --
--  ENUM: ticket type
-- ------------------------------------------------------------------ --

DO $$ BEGIN
    CREATE TYPE ticket_type AS ENUM ('task', 'story', 'bug');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ------------------------------------------------------------------ --
--  project_ticket_counters — auto-increment key per project
-- ------------------------------------------------------------------ --

CREATE TABLE IF NOT EXISTS project_ticket_counters (
    project_id UUID PRIMARY KEY REFERENCES projects (id) ON DELETE CASCADE,
    counter    INTEGER NOT NULL DEFAULT 0
);

-- ------------------------------------------------------------------ --
--  project_tickets — tickets on the board
-- ------------------------------------------------------------------ --

CREATE TABLE IF NOT EXISTS project_tickets (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID         NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    column_id    UUID         NOT NULL REFERENCES project_board_columns (id) ON DELETE CASCADE,
    assignee_id  UUID         REFERENCES auth_users (id) ON DELETE SET NULL,
    created_by   UUID         NOT NULL REFERENCES auth_users (id) ON DELETE RESTRICT,

    ticket_key   VARCHAR(20)      NOT NULL,
    title        TEXT             NOT NULL,
    description  TEXT,
    priority     ticket_priority  NOT NULL DEFAULT 'medium',
    type         ticket_type      NOT NULL DEFAULT 'task',
    labels       JSONB            NOT NULL DEFAULT '[]',
    due_date     DATE,
    position     INTEGER          NOT NULL DEFAULT 0,

    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_project_tickets_key UNIQUE (project_id, ticket_key)
);

CREATE INDEX IF NOT EXISTS idx_project_tickets_project_id
    ON project_tickets (project_id);

CREATE INDEX IF NOT EXISTS idx_project_tickets_column_id
    ON project_tickets (column_id);

CREATE INDEX IF NOT EXISTS idx_project_tickets_assignee_id
    ON project_tickets (assignee_id);

CREATE INDEX IF NOT EXISTS idx_project_tickets_project_column_position
    ON project_tickets (project_id, column_id, position);