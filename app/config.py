"""Application defaults — read from environment variables to avoid hardcoding passwords"""
from __future__ import annotations

import os
import pathlib
import secrets


def _load_local_env() -> None:
    """อ่าน .env.local (driver/server ที่เครื่องนั้นใช้ได้) ถ้ามี

    bootstrap.py เขียนไฟล์นี้ให้ตอนเตรียมเครื่องใหม่ — ค่าที่มีอยู่แล้วใน
    environment variable จะไม่ถูกทับ
    """
    env_file = pathlib.Path(__file__).resolve().parent.parent / ".env.local"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_local_env()


def _connection_string() -> str:
    driver = os.environ.get("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")
    server = os.environ.get("MSSQL_SERVER", r".\SQLEXPRESS")
    database = os.environ.get("MSSQL_DATABASE", "MusicStreamingDB")
    trusted = os.environ.get("MSSQL_TRUSTED", "yes").lower() in ("1", "yes", "true")

    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server}",
        f"DATABASE={database}",
        "Trusted_Connection=yes" if trusted else "",
        "TrustServerCertificate=yes",
        "Encrypt=yes",
        "APP=dsh-music-web",
    ]
    return ";".join(p for p in parts if p) + ";"


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    CONNECTION_STRING = _connection_string()

    # Items per page (simple pagination with TOP)
    PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "20"))

    # App name shown in the site header
    APP_NAME = os.environ.get("APP_NAME", "Plern")
