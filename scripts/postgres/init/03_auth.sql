-- Auth tables for TicketForge user authentication.
-- Runs after 01_extensions.sql and 02_schema.sql.
-- Adds auth_users and refresh_tokens alongside the existing
-- users, tickets, and assignments tables.

-- ------------------------------------------------------------------ --
--  auth_users — registered user accounts
-- ------------------------------------------------------------------ --

CREATE TABLE IF NOT EXISTS auth_users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username      VARCHAR(30)  NOT NULL,
    first_name    VARCHAR(50)  NOT NULL,
    last_name     VARCHAR(50)  NOT NULL,
    email         VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_auth_users_username UNIQUE (username),
    CONSTRAINT uq_auth_users_email    UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS idx_auth_users_email
    ON auth_users (email);

CREATE INDEX IF NOT EXISTS idx_auth_users_username
    ON auth_users (username);


-- ------------------------------------------------------------------ --
--  refresh_tokens — hashed refresh tokens for session management
-- ------------------------------------------------------------------ --

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID         NOT NULL REFERENCES auth_users (id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ  NOT NULL,
    revoked    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id
    ON refresh_tokens (user_id);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash
    ON refresh_tokens (token_hash);