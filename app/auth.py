"""
การยืนยันตัวตน: hash/verify รหัสผ่าน + decorator บังคับ login

ทำไมไม่เก็บ plaintext ในคอลัมน์ Password:
    ถ้าฐานข้อมูลรั่ว ผู้ใช้มักใช้รหัสเดิมกับเว็บอื่นด้วย -> เสียหายเป็นลูกโซ่
    เราใช้ PBKDF2-HMAC-SHA256 (work factor 200,000 รอบ + salt สุ่มต่อคน)
    ซึ่งเป็นฟังก์ชันที่มีอยู่ใน standard library ไม่ต้องลง library เพิ่ม

รูปแบบที่เก็บในคอลัมน์ dbo.[User].Password
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
        # compare_digest กัน timing attack
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
