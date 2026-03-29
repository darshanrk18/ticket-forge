"""Auth route handlers.

Thin layer — parse request, call service, set cookies, return response.
No business logic lives here.
"""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from web_backend.constants.auth import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from web_backend.database import get_db
from web_backend.models.user import AuthUser
from web_backend.schemas.auth import (
    AuthResponse,
    MessageResponse,
    SigninRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from web_backend.security.dependencies import get_current_user
from web_backend.services.auth import (
    authenticate_user,
    create_user,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set the refresh token as an HttpOnly secure cookie."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,  # Set True in production (HTTPS)
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Remove the refresh token cookie."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
    )


# ------------------------------------------------------------------ #
#  POST /auth/signup
# ------------------------------------------------------------------ #


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def signup(
    data: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Create a new account and return tokens (auto-login)."""
    try:
        user, access_token, raw_refresh = await create_user(db, data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    _set_refresh_cookie(response, raw_refresh)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
    )


# ------------------------------------------------------------------ #
#  POST /auth/signin
# ------------------------------------------------------------------ #


@router.post("/signin", response_model=AuthResponse)
async def signin(
    data: SigninRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Authenticate with email/username + password."""
    try:
        user, access_token, raw_refresh = await authenticate_user(db, data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    _set_refresh_cookie(response, raw_refresh)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
    )


# ------------------------------------------------------------------ #
#  POST /auth/refresh
# ------------------------------------------------------------------ #


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME),
) -> TokenResponse:
    """Issue a new access token using the refresh cookie."""
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    try:
        _, access_token, new_raw_refresh = await rotate_refresh_token(db, refresh_token)
    except ValueError as exc:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    _set_refresh_cookie(response, new_raw_refresh)

    return TokenResponse(access_token=access_token)


# ------------------------------------------------------------------ #
#  GET /auth/me
# ------------------------------------------------------------------ #


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: AuthUser = Depends(get_current_user),
) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse.model_validate(current_user)


# ------------------------------------------------------------------ #
#  POST /auth/logout
# ------------------------------------------------------------------ #


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
    refresh_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME),
) -> MessageResponse:
    """Revoke refresh token and clear cookie."""
    await revoke_refresh_token(db, refresh_token)
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out successfully")
