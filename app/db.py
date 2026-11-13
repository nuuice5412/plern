"""
Database access layer

Principle: all queries live here and in routes.py, using parameterized (?) calls
No SQL string concatenation with user input => prevents SQL Injection
"""
from __future__ import annotations

import re
from typing import Any, Sequence

import pyodbc
from flask import current_app, g


# ---------------------------------------------------------------------------
# connection lifecycle (one connection per request)
# ---------------------------------------------------------------------------
def get_conn() -> pyodbc.Connection:
    if "db_conn" not in g:
        g.db_conn = pyodbc.connect(
            current_app.config["CONNECTION_STRING"],
            timeout=10,
            autocommit=True,
        )
    return g.db_conn


def close_conn(exc: BaseException | None = None) -> None:
    conn = g.pop("db_conn", None)
    if conn is not None:
        conn.close()


def init_app(app) -> None:
    app.teardown_appcontext(close_conn)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _rows_to_dicts(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    if cursor.description is None:
        return []
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def query(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    """SELECT multiple rows -> list[dict]"""
    cursor = get_conn().cursor()
    try:
        cursor.execute(sql, tuple(params))
        return _rows_to_dicts(cursor)
    finally:
        cursor.close()


def query_one(sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    """SELECT a single row -> dict | None"""
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """Direct INSERT/UPDATE/DELETE (no procedure) -> affected row count"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, tuple(params))
        if not conn.autocommit:
            conn.commit()
        return cursor.rowcount
    except pyodbc.Error:
        if not conn.autocommit:
            conn.rollback()
        raise
    finally:
        cursor.close()


def call_proc(batch: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    """
    Call a stored procedure that has an OUTPUT parameter

    pyodbc has no direct API for SQL Server output parameters, so we wrap it in a batch:
        DECLARE @out INT;
        EXEC dbo.usp_X @A = ?, @Out = @out OUTPUT;
        SELECT @out AS out;
    then read the value from the final result set
    """
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(batch, tuple(params))
        # Skip result sets until the final SELECT
        while cursor.description is None:
            if not cursor.nextset():
                return []
        return _rows_to_dicts(cursor)
    except pyodbc.Error:
        if not conn.autocommit:
            conn.rollback()
        raise
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Convert SQL Server errors into messages that can be shown on the web page
# ---------------------------------------------------------------------------
_MSG_RE = re.compile(r"\[SQL Server\](.*?)(?:\s*\(\d+\))?\s*(?:\(SQLExecDirectW\))?$", re.S)


def db_message(exc: Exception) -> str:
    """
    pyodbc.Error looks like
        ('42000', "[42000] [Microsoft][ODBC Driver 18][SQL Server]message (50001) (SQLExecDirectW)")
    This function extracts just the "message"
    """
    text = str(exc)
    match = _MSG_RE.search(text)
    if match:
        msg = match.group(1).strip()
        if msg:
            return msg
    # fallback: take the last chunk after the final [...]
    chunks = re.split(r"\[[^\]]*\]", text)
    tail = chunks[-1].strip(" )'\"\n")
    return tail or "เกิดข้อผิดพลาดจากฐานข้อมูล"
