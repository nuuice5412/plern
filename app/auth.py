"""
Authentication: hash/verify passwords + a decorator that enforces login

Why we don't store plaintext in the Password column:
    If the database leaks, users often reuse the same password on other sites -> the damage cascades.
    We use PBKDF2-HMAC-SHA256 (work factor 200,000 rounds + a random salt per user),
    which ships with the standard library, so no extra library is needed.

Format stored in the dbo.[User].Password column
    pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>
"""
from __future__ import annotations

import functools
import hashlib
import hmac
import os

from flask import flash, g, redirect, request, url_for

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 200_000
SALT_BYTES = 16
KEY_BYTES = 32


def hash_password(password: str) -> str:
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS, KEY_BYTES)
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, hash_hex = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                     int(iterations), len(expected))
        # compare_digest prevents timing attacks
        return hmac.compare_digest(actual, expected)
    except (ValueError, AttributeError, TypeError):
        return False


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            flash("กรุณาเข้าสู่ระบบก่อนครับ", "warning")
            return redirect(url_for("main.login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapped
