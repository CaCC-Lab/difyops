"""Dify password management via direct database access.

Used when the original password is unknown and Console API
login is not possible. Generates PBKDF2-SHA256 hashes
compatible with Dify's internal password storage.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import subprocess
from dataclasses import dataclass


@dataclass
class PasswordHash:
    """PBKDF2 password hash and salt in Dify's storage format."""

    password_b64: str
    salt_b64: str


def generate_hash(password: str) -> PasswordHash:
    """Generate a Dify-compatible password hash.

    Dify uses PBKDF2-HMAC-SHA256 with 10000 iterations.
    The hash is hex-encoded, then Base64-encoded.
    The salt is 16 random bytes, Base64-encoded.

    Args:
        password: Plaintext password

    Returns:
        PasswordHash with Base64-encoded hash and salt
    """
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 10000)
    pw_hex = binascii.hexlify(dk)
    return PasswordHash(
        password_b64=base64.b64encode(pw_hex).decode("utf-8"),
        salt_b64=base64.b64encode(salt).decode("utf-8"),
    )


def reset_via_docker(
    email: str,
    new_password: str,
    container_name: str = "dify-db",
    db_name: str = "dify",
    db_user: str = "postgres",
) -> bool:
    """Reset a Dify account password by updating the database directly.

    Requires Docker access to the dify-db container.

    Args:
        email: Account email
        new_password: New plaintext password
        container_name: Docker container name for PostgreSQL
        db_name: Database name
        db_user: Database user

    Returns:
        True if the password was updated successfully
    """
    pw_hash = generate_hash(new_password)
    sql = "UPDATE accounts SET password = :'pw', password_salt = :'salt' WHERE email = :'email';"
    result = subprocess.run(
        [
            "docker",
            "exec",
            container_name,
            "psql",
            "-U",
            db_user,
            "-d",
            db_name,
            "-v",
            f"pw={pw_hash.password_b64}",
            "-v",
            f"salt={pw_hash.salt_b64}",
            "-v",
            f"email={email}",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
    )
    return "UPDATE 1" in result.stdout
