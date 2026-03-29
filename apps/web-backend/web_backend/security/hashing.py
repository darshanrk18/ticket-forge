"""Password hashing utilities using bcrypt."""

import bcrypt

from web_backend.constants.auth import BCRYPT_ROUNDS


def hash_password(plain: str) -> str:
    """Hash a plaintext password and return the bcrypt string."""
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain.encode(), salt).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())
