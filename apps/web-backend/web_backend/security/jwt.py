"""JWT token creation and validation."""

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from web_backend.config import get_settings
from web_backend.constants.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    TOKEN_ALGORITHM,
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
)


def create_access_token(
    user_id: uuid.UUID,
    username: str,
    email: str,
) -> str:
    """Create a short-lived access token."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "username": username,
        "email": email,
        "type": TOKEN_TYPE_ACCESS,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(
        payload,
        get_settings().jwt_secret_key,
        algorithm=TOKEN_ALGORITHM,
    )


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str, datetime]:
    """Create a long-lived refresh token.

    Returns:
      Tuple of (raw_token, jti, expires_at).
      The ``jti`` is stored hashed in the DB for revocation checks.
    """
    now = datetime.now(UTC)
    jti = str(uuid.uuid4())
    expires_at = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "jti": jti,
        "type": TOKEN_TYPE_REFRESH,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(
        payload,
        get_settings().jwt_secret_key,
        algorithm=TOKEN_ALGORITHM,
    )
    return token, jti, expires_at


def decode_access_token(token: str) -> dict:
    """Decode and validate an access token.

    Raises:
      JWTError: If the token is expired, malformed, or not an access token.
    """
    payload = jwt.decode(
        token,
        get_settings().jwt_secret_key,
        algorithms=[TOKEN_ALGORITHM],
    )
    if payload.get("type") != TOKEN_TYPE_ACCESS:
        msg = "Invalid token type"
        raise JWTError(msg)
    return payload


def decode_refresh_token(token: str) -> dict:
    """Decode and validate a refresh token.

    Raises:
      JWTError: If the token is expired, malformed, or not a refresh token.
    """
    payload = jwt.decode(
        token,
        get_settings().jwt_secret_key,
        algorithms=[TOKEN_ALGORITHM],
    )
    if payload.get("type") != TOKEN_TYPE_REFRESH:
        msg = "Invalid token type"
        raise JWTError(msg)
    return payload
