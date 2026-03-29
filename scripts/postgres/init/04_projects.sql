-- Project tables for TicketForge multi-tenant project system.
-- Runs after 03_auth.sql.
-- Adds projects, project_members, and bridges auth_users ↔ users.

-- ------------------------------------------------------------------ --
--  ENUM: project member roles
-- ------------------------------------------------------------------ --

DO $$ BEGIN
    CREATE TYPE project_role AS ENUM ('owner', 'admin', 'member');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;


-- ------------------------------------------------------------------ --
--  projects — top-level project/board container
-- ------------------------------------------------------------------ --

CREATE TABLE IF NOT EXISTS projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) NOT NULL,
    slug        VARCHAR(100) NOT NULL,
    description TEXT,
    created_by  UUID         NOT NULL REFERENCES auth_users (id) ON DELETE RESTRICT,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_projects_slug UNIQUE (slug)
);

CREATE INDEX IF NOT EXISTS idx_projects_slug
    ON projects (slug);

CREATE INDEX IF NOT EXISTS idx_projects_created_by
    ON projects (created_by);


-- ------------------------------------------------------------------ --
--  project_members — who belongs to which project, with what role
-- ------------------------------------------------------------------ --

CREATE TABLE IF NOT EXISTS project_members (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID         NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    user_id    UUID         NOT NULL REFERENCES auth_users (id) ON DELETE CASCADE,
    role       project_role NOT NULL DEFAULT 'member',
    joined_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_project_members_project_user UNIQUE (project_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_project_members_project_id
    ON project_members (project_id);

CREATE INDEX IF NOT EXISTS idx_project_members_user_id
    ON project_members (user_id);


-- ------------------------------------------------------------------ --
--  project_board_columns — configurable kanban columns per project
-- ------------------------------------------------------------------ --

CREATE TABLE IF NOT EXISTS project_board_columns (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID         NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    name       VARCHAR(50)  NOT NULL,
    position   INTEGER      NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_board_columns_project_position UNIQUE (project_id, position),
    CONSTRAINT uq_board_columns_project_name     UNIQUE (project_id, name)
);

CREATE INDEX IF NOT EXISTS idx_board_columns_project_id
    ON project_board_columns (project_id);


-- ------------------------------------------------------------------ --
--  Bridge: auth_users → users (ML profile)
--  Nullable because ML profile is created later (resume upload or
--  first ticket close). The FK target is users.member_id (BIGINT).
-- ------------------------------------------------------------------ --

ALTER TABLE auth_users
    ADD COLUMN IF NOT EXISTS member_id BIGINT;

-- Only add the FK constraint if it doesn't already exist
DO $$ BEGIN
    ALTER TABLE auth_users
        ADD CONSTRAINT fk_auth_users_member_id
        FOREIGN KEY (member_id) REFERENCES users (member_id)
        ON DELETE SET NULL;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_auth_users_member_id
    ON auth_users (member_id);


-- ------------------------------------------------------------------ --
--  Bridge: tickets → projects
--  Nullable to keep backward-compat with existing ML pipeline tickets
--  that were ingested before the project system existed.
-- ------------------------------------------------------------------ --

ALTER TABLE tickets
    ADD COLUMN IF NOT EXISTS project_id UUID;

DO $$ BEGIN
    ALTER TABLE tickets
        ADD CONSTRAINT fk_tickets_project_id
        FOREIGN KEY (project_id) REFERENCES projects (id)
        ON DELETE SET NULL;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_tickets_project_id
    ON tickets (project_id);