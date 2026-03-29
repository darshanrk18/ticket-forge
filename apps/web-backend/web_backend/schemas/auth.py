"""Pydantic request/response schemas for auth endpoints."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

# ------------------------------------------------------------------ #
#  Validators (reusable)
# ------------------------------------------------------------------ #

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")
PASSWORD_MIN_LENGTH = 8


def _validate_username(value: str) -> str:
    """Enforce 3-30 alphanumeric + underscore characters."""
    if not USERNAME_PATTERN.match(value):
        msg = "Username must contain only letters, numbers, and underscores"
        raise ValueError(msg)
    return value.lower()


def _validate_password(value: str) -> str:
    """Enforce min 8 chars, 1 upper, 1 lower, 1 digit."""
    if len(value) < PASSWORD_MIN_LENGTH:
        msg = f"Password must be at least {PASSWORD_MIN_LENGTH} characters"
        raise ValueError(msg)
    if not re.search(r"[A-Z]", value):
        msg = "Password must contain at least one uppercase letter"
        raise ValueError(msg)
    if not re.search(r"[a-z]", value):
        msg = "Password must contain at least one lowercase letter"
        raise ValueError(msg)
    if not re.search(r"\d", value):
        msg = "Password must contain at least one digit"
        raise ValueError(msg)
    return value


# ------------------------------------------------------------------ #
#  Requests
# ------------------------------------------------------------------ #


class SignupRequest(BaseModel):
    """POST /auth/signup request body."""

    username: str = Field(..., min_length=3, max_length=30, examples=["johndoe"])
    first_name: str = Field(..., min_length=1, max_length=50, examples=["John"])
    last_name: str = Field(..., min_length=1, max_length=50, examples=["Doe"])
    email: EmailStr = Field(..., examples=["john@example.com"])
    password: str = Field(..., min_length=8, examples=["SecurePass123!"])

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        """Validate username format."""
        return _validate_username(v)

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        """Validate password strength."""
        return _validate_password(v)


class SigninRequest(BaseModel):
    """POST /auth/signin request body.

    The ``login`` field accepts either an email or a username.
    """

    login: str = Field(
        ...,
        min_length=3,
        examples=["john@example.com"],
        description="Email address or username",
    )
    password: str = Field(..., min_length=1)


# ------------------------------------------------------------------ #
#  Responses
# ------------------------------------------------------------------ #


class UserResponse(BaseModel):
    """Public user representation (no password hash)."""

    id: uuid.UUID
    username: str
    first_name: str
    last_name: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Returned on signup and signin — user + access token."""

    user: UserResponse
    access_token: str


class TokenResponse(BaseModel):
    """Returned on token refresh — new access token only."""

    access_token: str


class MessageResponse(BaseModel):
    """Generic message response (logout, etc.)."""

    message: str
