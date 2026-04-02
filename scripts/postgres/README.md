# Postgres + PgVector for Ticket-Forge

This folder contains the database setup for storing **engineered features** and **embeddings** in a single Postgres database using the PgVector extension. Supports **hybrid search** (semantic vector + lexical full-text) for the Multi-Modal Retrieval Engine.

## Quick start

From the repo root:

```bash
docker compose up -d
```

The init scripts in `init/` run automatically on first start and create the extensions and schema.

## Connection

- **Host:** localhost
- **Port:** 5432
- **User:** ticketforge
- **Password:** ticketforge
- **Database:** ticketforge

```bash
psql -h localhost -U ticketforge -d ticketforge
```

## Schema

### Users Table
Engineer profiles with dynamic profile vectors that evolve as tickets are completed.

| Column | Type | Description |
|--------|------|-------------|
| `member_id` | UUID (PK) | Primary key identifying the engineer |
| `full_name` | TEXT | Engineer's full name |
| `resume_base_vector` | vector(384) | Original embedding from resume (cold start) |
| `profile_vector` | vector(384) | Dynamic centroid embedding (updated via moving average) |
| `skill_keywords` | tsvector | Weighted keywords for hybrid keyword search |
| `tickets_closed_count` | INTEGER | Number of tickets closed (weight for profile confidence) |
| `created_at`, `updated_at` | TIMESTAMPTZ | Timestamps |

### Tickets Table
Ticket/issue records with semantic embeddings and metadata.

| Column | Type | Description |
|--------|------|-------------|
| `ticket_id` | TEXT (PK) | Original ticket ID from GitHub/Jira |
| `title` | TEXT | Ticket title (for keyword search) |
| `description` | TEXT | Full ticket description (for keyword search) |
| `ticket_vector` | vector(384) | Semantic embedding of ticket content |
| `labels` | JSONB | Array of tags (e.g., `["bug", "priority:high"]`) |
| `status` | ENUM | `open`, `in-progress`, `closed` |
| `resolution_time_actual` | INTERVAL | Ground truth resolution time (for training) |
| `created_at`, `updated_at` | TIMESTAMPTZ | Timestamps |

### Assignments Table
Tracks ticket-to-engineer assignments for profile updates.

| Column | Type | Description |
|--------|------|-------------|
| `assignment_id` | UUID (PK) | Primary key |
| `ticket_id` | TEXT (FK) | References `tickets.ticket_id` |
| `engineer_id` | UUID (FK) | References `users.member_id` |
| `assigned_at` | TIMESTAMPTZ | Assignment timestamp |
| `replayed_at` | TIMESTAMPTZ | Timestamp set after the assignment has been applied to profile replay |

## Indexes

- **Vector indexes (IVFFlat):** `profile_vector`, `resume_base_vector`, `ticket_vector` for cosine similarity (`<=>`)
- **Full-text indexes (GIN):** `skill_keywords`, `title`, `description` for hybrid search
- **JSONB index (GIN):** `labels` for filtering by tags
- **Foreign keys:** Proper referential integrity on assignments
- **Replay tracking index:** `replayed_at` supports idempotent closed-ticket replay

## Scripts

- **`init/01_extensions.sql`** – Enables `vector` and `pg_trgm` extensions
- **`init/02_schema.sql`** – Creates `users`, `tickets`, `assignments` tables, ENUMs, and indexes
- **`example_queries.sql`** – Example INSERT, SELECT, hybrid search, and profile update patterns

## Example queries

See `example_queries.sql` for:

1. Insert user with resume/profile vectors and skill keywords
2. Insert ticket with vector and JSONB labels
3. Create assignment
4. Semantic search (vector similarity)
5. Lexical search (full-text on skill keywords)
6. **Hybrid search with RRF** (Reciprocal Rank Fusion)
7. Update profile vector (moving average with decay)
8. Update skill keywords from closed tickets
9. Query tickets by JSONB labels
10. Assignment history
11. Aggregate statistics
12. Table row counts

## Hybrid Search

The system uses **Reciprocal Rank Fusion (RRF)** to combine:
- **Semantic path:** Vector similarity (`profile_vector <=> ticket_vector`)
- **Lexical path:** Full-text search (`skill_keywords @@ to_tsquery(...)`)

RRF formula: `score = 1/(k + rank_semantic) + 1/(k + rank_lexical)` where `k=60`.

Similarity is computed with the `<=>` operator (cosine distance); lower is more similar. Use `1 - (embedding <=> query_embedding)` for a similarity score in [0, 1].
