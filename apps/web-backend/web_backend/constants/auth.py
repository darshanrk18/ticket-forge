"""Auth-related constants.

Single source of truth for token lifetimes, cookie names,
hashing rounds, and JWT algorithm. Change here, applies everywhere.
"""

# JWT
TOKEN_ALGORITHM = "HS256"
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# Token lifetimes
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Bcrypt
BCRYPT_ROUNDS = 12

# Cookie
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"
