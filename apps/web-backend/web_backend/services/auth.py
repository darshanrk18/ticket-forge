"""Auth business logic.

Handles user creation, credential verification, refresh token
rotation, and logout. Routes call these — no DB or hashing in routes.
"""

import hashlib
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from web_backend.models.user import AuthUser, RefreshToken
from web_backend.schemas.auth import SigninRequest, SignupRequest
from web_backend.security.hashing import hash_password, verify_password
from web_backend.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)


def _hash_jti(jti: str) -> str:
    """SHA-256 hash of the JTI for DB storage (not reversible)."""
    return hashlib.sha256(jti.encode()).hexdigest()


# ------------------------------------------------------------------ #
#  Signup
# ------------------------------------------------------------------ #


async def create_user(
    db: AsyncSession,
    data: SignupRequest,
) -> tuple[AuthUser, str, str]:
    """Create a new user and issue tokens.

    Returns:
      Tuple of (user, access_token, raw_refresh_token).

    Raises:
      ValueError: If username or email already taken.
    """
    result = await db.execute(
        select(AuthUser).where(
            or_(
                AuthUser.username == data.username,
                AuthUser.email == data.email,
            )
        )
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        if existing.username == data.username:
            msg = "Username already taken"
            raise ValueError(msg)
        msg = "Email already registered"
        raise ValueError(msg)

    user = AuthUser(
        username=data.username,
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()

    access_token = create_access_token(user.id, user.username, user.email)
    raw_refresh, jti, expires_at = create_refresh_token(user.id)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_jti(jti),
            expires_at=expires_at,
        )
    )
    await db.commit()
    await db.refresh(user)

    return user, access_token, raw_refresh


# ------------------------------------------------------------------ #
#  Signin
# ------------------------------------------------------------------ #


async def authenticate_user(
    db: AsyncSession,
    data: SigninRequest,
) -> tuple[AuthUser, str, str]:
    """Verify credentials and issue tokens.

    The ``login`` field is treated as email if it contains ``@``,
    otherwise as username.

    Returns:
      Tuple of (user, access_token, raw_refresh_token).

    Raises:
      ValueError: If credentials are invalid.
    """
    is_email = "@" in data.login
    condition = (
        AuthUser.email == data.login
        if is_email
        else AuthUser.username == data.login.lower()
    )

    result = await db.execute(
        select(AuthUser).where(condition, AuthUser.is_active.is_(True))
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(data.password, user.password_hash):
        msg = "Invalid credentials"
        raise ValueError(msg)

    access_token = create_access_token(user.id, user.username, user.email)
    raw_refresh, jti, expires_at = create_refresh_token(user.id)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_jti(jti),
            expires_at=expires_at,
        )
    )
    await db.commit()

    return user, access_token, raw_refresh


# ------------------------------------------------------------------ #
#  Refresh
# ------------------------------------------------------------------ #


async def rotate_refresh_token(
    db: AsyncSession,
    raw_token: str,
) -> tuple[uuid.UUID, str, str]:
    """Validate a refresh token, revoke it, and issue a new pair.

    Returns:
      Tuple of (user_id, new_access_token, new_raw_refresh_token).

    Raises:
      ValueError: If the token is invalid, expired, or already revoked.
    """
    try:
        payload = decode_refresh_token(raw_token)
    except Exception as exc:
        msg = "Invalid refresh token"
        raise ValueError(msg) from exc

    jti = payload.get("jti")
    user_id = uuid.UUID(payload["sub"])

    if jti is None:
        msg = "Invalid refresh token"
        raise ValueError(msg)

    token_hash = _hash_jti(jti)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked.is_(False),
        )
    )
    stored = result.scalar_one_or_none()

    if stored is None:
        msg = "Refresh token revoked or not found"
        raise ValueError(msg)

    # Revoke old
    stored.revoked = True

    # Fetch user for new access token claims
    user_result = await db.execute(
        select(AuthUser).where(AuthUser.id == user_id, AuthUser.is_active.is_(True))
    )
    user = user_result.scalar_one_or_none()

    if user is None:
        msg = "User not found or inactive"
        raise ValueError(msg)

    # Issue new pair
    access_token = create_access_token(user.id, user.username, user.email)
    new_raw_refresh, new_jti, expires_at = create_refresh_token(user.id)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_jti(new_jti),
            expires_at=expires_at,
        )
    )
    await db.commit()

    return user_id, access_token, new_raw_refresh


# ------------------------------------------------------------------ #
#  Logout
# ------------------------------------------------------------------ #


async def revoke_refresh_token(
    db: AsyncSession,
    raw_token: str | None,
) -> None:
    """Revoke a refresh token so it cannot be reused.

    Silently succeeds if the token is already revoked or missing.
    """
    if raw_token is None:
        return

    try:
        payload = decode_refresh_token(raw_token)
    except Exception:
        return

    jti = payload.get("jti")
    if jti is None:
        return

    token_hash = _hash_jti(jti)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked.is_(False),
        )
    )
    stored = result.scalar_one_or_none()

    if stored is not None:
        stored.revoked = True
        await db.commit()
