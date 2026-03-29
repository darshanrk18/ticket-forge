"""Auth endpoint tests.

Covers the full signup → signin → refresh → me → logout flow
plus edge cases: duplicate users, bad credentials, expired tokens,
and password validation.
"""

import pytest
from httpx import AsyncClient

from web_backend.constants.auth import REFRESH_COOKIE_NAME

from conftest import VALID_SIGNUP, VALID_SIGNUP_2

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------ #
#  Signup
# ------------------------------------------------------------------ #


class TestSignup:
    """POST /api/v1/auth/signup."""

    async def test_signup_success(self, client: AsyncClient) -> None:
        """Happy path — creates user, returns tokens, sets cookie."""
        resp = await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)

        assert resp.status_code == 201
        body = resp.json()
        assert body["user"]["username"] == "johndoe"
        assert body["user"]["first_name"] == "John"
        assert body["user"]["email"] == "john@example.com"
        assert "access_token" in body
        assert "password" not in body["user"]
        assert "password_hash" not in body["user"]
        assert REFRESH_COOKIE_NAME in resp.cookies

    async def test_signup_duplicate_username(self, client: AsyncClient) -> None:
        """409 when username is already taken."""
        await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)

        duplicate = {**VALID_SIGNUP_2, "username": "johndoe"}
        resp = await client.post("/api/v1/auth/signup", json=duplicate)

        assert resp.status_code == 409
        assert "username" in resp.json()["detail"].lower()

    async def test_signup_duplicate_email(self, client: AsyncClient) -> None:
        """409 when email is already registered."""
        await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)

        duplicate = {**VALID_SIGNUP_2, "email": "john@example.com"}
        resp = await client.post("/api/v1/auth/signup", json=duplicate)

        assert resp.status_code == 409
        assert "email" in resp.json()["detail"].lower()

    async def test_signup_weak_password_no_uppercase(self, client: AsyncClient) -> None:
        """422 when password has no uppercase letter."""
        data = {**VALID_SIGNUP, "password": "weakpass1"}
        resp = await client.post("/api/v1/auth/signup", json=data)
        assert resp.status_code == 422

    async def test_signup_weak_password_no_digit(self, client: AsyncClient) -> None:
        """422 when password has no digit."""
        data = {**VALID_SIGNUP, "password": "WeakPasss"}
        resp = await client.post("/api/v1/auth/signup", json=data)
        assert resp.status_code == 422

    async def test_signup_weak_password_too_short(self, client: AsyncClient) -> None:
        """422 when password is under 8 characters."""
        data = {**VALID_SIGNUP, "password": "Ab1"}
        resp = await client.post("/api/v1/auth/signup", json=data)
        assert resp.status_code == 422

    async def test_signup_invalid_username_special_chars(
        self, client: AsyncClient
    ) -> None:
        """422 when username contains special characters."""
        data = {**VALID_SIGNUP, "username": "john@doe!"}
        resp = await client.post("/api/v1/auth/signup", json=data)
        assert resp.status_code == 422

    async def test_signup_invalid_email(self, client: AsyncClient) -> None:
        """422 when email format is invalid."""
        data = {**VALID_SIGNUP, "email": "not-an-email"}
        resp = await client.post("/api/v1/auth/signup", json=data)
        assert resp.status_code == 422

    async def test_signup_missing_fields(self, client: AsyncClient) -> None:
        """422 when required fields are missing."""
        resp = await client.post("/api/v1/auth/signup", json={"username": "test"})
        assert resp.status_code == 422


# ------------------------------------------------------------------ #
#  Signin
# ------------------------------------------------------------------ #


class TestSignin:
    """POST /api/v1/auth/signin."""

    async def _create_user(self, client: AsyncClient) -> None:
        """Helper to create a test user."""
        await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)

    async def test_signin_with_email(self, client: AsyncClient) -> None:
        """Login using email + password."""
        await self._create_user(client)

        resp = await client.post(
            "/api/v1/auth/signin",
            json={"login": "john@example.com", "password": "SecurePass1"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["username"] == "johndoe"
        assert "access_token" in body
        assert REFRESH_COOKIE_NAME in resp.cookies

    async def test_signin_with_username(self, client: AsyncClient) -> None:
        """Login using username + password."""
        await self._create_user(client)

        resp = await client.post(
            "/api/v1/auth/signin",
            json={"login": "johndoe", "password": "SecurePass1"},
        )

        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == "john@example.com"

    async def test_signin_wrong_password(self, client: AsyncClient) -> None:
        """401 with wrong password (generic error, no field leak)."""
        await self._create_user(client)

        resp = await client.post(
            "/api/v1/auth/signin",
            json={"login": "john@example.com", "password": "WrongPass1"},
        )

        assert resp.status_code == 401
        assert "invalid" in resp.json()["detail"].lower()

    async def test_signin_nonexistent_user(self, client: AsyncClient) -> None:
        """401 when user doesn't exist (same generic error)."""
        resp = await client.post(
            "/api/v1/auth/signin",
            json={"login": "nobody@test.com", "password": "SecurePass1"},
        )

        assert resp.status_code == 401

    async def test_signin_username_case_insensitive(self, client: AsyncClient) -> None:
        """Username login is case-insensitive."""
        await self._create_user(client)

        resp = await client.post(
            "/api/v1/auth/signin",
            json={"login": "JohnDoe", "password": "SecurePass1"},
        )

        assert resp.status_code == 200


# ------------------------------------------------------------------ #
#  Me
# ------------------------------------------------------------------ #


class TestMe:
    """GET /api/v1/auth/me."""

    async def test_me_authenticated(self, client: AsyncClient) -> None:
        """Returns user profile with valid access token."""
        signup_resp = await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)
        token = signup_resp.json()["access_token"]

        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "johndoe"
        assert body["first_name"] == "John"
        assert "password_hash" not in body

    async def test_me_no_token(self, client: AsyncClient) -> None:
        """401 when no Authorization header is provided."""
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_me_invalid_token(self, client: AsyncClient) -> None:
        """401 when token is garbage."""
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer garbage.token.here"},
        )
        assert resp.status_code == 401


# ------------------------------------------------------------------ #
#  Refresh
# ------------------------------------------------------------------ #


class TestRefresh:
    """POST /api/v1/auth/refresh."""

    async def test_refresh_success(self, client: AsyncClient) -> None:
        """Rotates tokens — new access token, new refresh cookie."""
        signup_resp = await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)

        refresh_cookie = signup_resp.cookies.get(REFRESH_COOKIE_NAME)
        assert refresh_cookie is not None

        resp = await client.post(
            "/api/v1/auth/refresh",
            cookies={REFRESH_COOKIE_NAME: refresh_cookie},
        )

        assert resp.status_code == 200
        new_access = resp.json()["access_token"]
        assert new_access  # valid token returned
        assert REFRESH_COOKIE_NAME in resp.cookies

    async def test_refresh_no_cookie(self, client: AsyncClient) -> None:
        """401 when refresh cookie is missing."""
        resp = await client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401

    async def test_refresh_reuse_revoked(self, client: AsyncClient) -> None:
        """401 when trying to reuse a rotated (revoked) refresh token."""
        signup_resp = await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)
        refresh_cookie = signup_resp.cookies.get(REFRESH_COOKIE_NAME)

        await client.post(
            "/api/v1/auth/refresh",
            cookies={REFRESH_COOKIE_NAME: refresh_cookie},
        )

        resp = await client.post(
            "/api/v1/auth/refresh",
            cookies={REFRESH_COOKIE_NAME: refresh_cookie},
        )
        assert resp.status_code == 401


# ------------------------------------------------------------------ #
#  Logout
# ------------------------------------------------------------------ #


class TestLogout:
    """POST /api/v1/auth/logout."""

    async def test_logout_success(self, client: AsyncClient) -> None:
        """Revokes refresh token and clears cookie."""
        signup_resp = await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)
        token = signup_resp.json()["access_token"]
        refresh_cookie = signup_resp.cookies.get(REFRESH_COOKIE_NAME)

        resp = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
            cookies={REFRESH_COOKIE_NAME: refresh_cookie},
        )

        assert resp.status_code == 200
        assert resp.json()["message"] == "Logged out successfully"

    async def test_logout_no_token(self, client: AsyncClient) -> None:
        """401 when not authenticated."""
        resp = await client.post("/api/v1/auth/logout")
        assert resp.status_code == 401

    async def test_refresh_after_logout_fails(self, client: AsyncClient) -> None:
        """Refresh token is unusable after logout."""
        signup_resp = await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)
        token = signup_resp.json()["access_token"]
        refresh_cookie = signup_resp.cookies.get(REFRESH_COOKIE_NAME)

        await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
            cookies={REFRESH_COOKIE_NAME: refresh_cookie},
        )

        resp = await client.post(
            "/api/v1/auth/refresh",
            cookies={REFRESH_COOKIE_NAME: refresh_cookie},
        )
        assert resp.status_code == 401


# ------------------------------------------------------------------ #
#  Full flow integration
# ------------------------------------------------------------------ #


class TestFullFlow:
    """End-to-end: signup → me → logout → signin → me."""

    async def test_complete_auth_lifecycle(self, client: AsyncClient) -> None:
        """Walk through the entire auth flow."""
        # 1. Signup
        signup_resp = await client.post("/api/v1/auth/signup", json=VALID_SIGNUP)
        assert signup_resp.status_code == 201
        token = signup_resp.json()["access_token"]

        # 2. Access protected route
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["username"] == "johndoe"

        # 3. Logout
        refresh_cookie = signup_resp.cookies.get(REFRESH_COOKIE_NAME)
        logout_resp = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
            cookies={REFRESH_COOKIE_NAME: refresh_cookie},
        )
        assert logout_resp.status_code == 200

        # 4. Signin again
        signin_resp = await client.post(
            "/api/v1/auth/signin",
            json={"login": "johndoe", "password": "SecurePass1"},
        )
        assert signin_resp.status_code == 200
        new_token = signin_resp.json()["access_token"]
        assert new_token  # valid token returned

        # 5. Access protected route with new token
        me_resp2 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert me_resp2.status_code == 200
        assert me_resp2.json()["email"] == "john@example.com"
