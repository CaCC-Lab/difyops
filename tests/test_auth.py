"""Tests for authentication module."""

import base64

from dify_admin.auth import DifySession, _extract_cookie
from dify_admin.password import generate_hash


class TestDifySession:
    def test_cookies(self) -> None:
        session = DifySession(
            access_token="at123", refresh_token="rt456", csrf_token="csrf789"
        )
        cookies = session.cookies()
        assert cookies["access_token"] == "at123"
        assert cookies["csrf_token"] == "csrf789"
        assert "refresh_token" not in cookies

    def test_headers(self) -> None:
        session = DifySession(
            access_token="at", refresh_token="rt", csrf_token="mycsrf"
        )
        headers = session.headers()
        assert headers["X-CSRF-Token"] == "mycsrf"


class TestPasswordHash:
    def test_generate_hash_format(self) -> None:
        pw_hash = generate_hash("TestPassword1")
        # Both should be valid base64
        base64.b64decode(pw_hash.password_b64)
        base64.b64decode(pw_hash.salt_b64)

    def test_generate_hash_deterministic_with_same_salt(self) -> None:
        # Different calls should produce different salts
        h1 = generate_hash("TestPassword1")
        h2 = generate_hash("TestPassword1")
        assert h1.salt_b64 != h2.salt_b64
        assert h1.password_b64 != h2.password_b64

    def test_generate_hash_different_passwords(self) -> None:
        h1 = generate_hash("Password1")
        h2 = generate_hash("Password2")
        assert h1.password_b64 != h2.password_b64
