"""Project-related constants."""

# ------------------------------------------------------------------ #
#  Roles
# ------------------------------------------------------------------ #

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"

# Roles that can manage members (invite, remove, change role)
MANAGEMENT_ROLES = {ROLE_OWNER, ROLE_ADMIN}

# ------------------------------------------------------------------ #
#  Default board columns for new projects
# ------------------------------------------------------------------ #

DEFAULT_BOARD_COLUMNS = [
    "Backlog",
    "To Do",
    "In Progress",
    "In Review",
    "Done",
]

# ------------------------------------------------------------------ #
#  Limits
# ------------------------------------------------------------------ #

MAX_BOARD_COLUMNS = 12
MAX_PROJECT_NAME_LENGTH = 100
MAX_SLUG_LENGTH = 100
