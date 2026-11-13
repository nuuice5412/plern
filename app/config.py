"""Application defaults — read from environment variables to avoid hardcoding passwords"""
from __future__ import annotations

import os
import secrets


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
