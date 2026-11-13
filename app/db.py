"""
ชั้นติดต่อฐานข้อมูล (data access layer)

หลักการ: ทุก query รวมอยู่ที่นี่และใน routes.py แบบ parameterized (?)
ไม่มีการต่อสตริง SQL ด้วยค่าจากผู้ใช้ => กัน SQL Injection
"""
from __future__ import annotations

import re
from typing import Any, Sequence

import pyodbc
from flask import current_app, g


# ---------------------------------------------------------------------------
# connection lifecycle (1 connection ต่อ 1 request)
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
    """SELECT หลายแถว -> list[dict]"""
    cursor = get_conn().cursor()
    try:
        cursor.execute(sql, tuple(params))
        return _rows_to_dicts(cursor)
    finally:
        cursor.close()


def query_one(sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    """SELECT แถวเดียว -> dict | None"""
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """INSERT/UPDATE/DELETE ตรง ๆ (ไม่ผ่าน procedure) -> จำนวนแถวที่กระทบ"""
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
    เรียก stored procedure ที่มี OUTPUT parameter

    pyodbc ไม่มี API ตรง ๆ สำหรับ output param ของ SQL Server เราจึงห่อด้วย batch:
        DECLARE @out INT;
        EXEC dbo.usp_X @A = ?, @Out = @out OUTPUT;
        SELECT @out AS out;
    แล้วอ่านค่าจาก result set สุดท้าย
    """
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(batch, tuple(params))
        # ข้าม result set ที่ไม่ใช่ SELECT สุดท้าย
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
# แปลง error ของ SQL Server เป็นข้อความที่เอาไปแสดงบนหน้าเว็บได้
# ---------------------------------------------------------------------------
_MSG_RE = re.compile(r"\[SQL Server\](.*?)(?:\s*\(\d+\))?\s*(?:\(SQLExecDirectW\))?$", re.S)


def db_message(exc: Exception) -> str:
    """
    pyodbc.Error มีหน้าตาเป็น
        ('42000', "[42000] [Microsoft][ODBC Driver 18][SQL Server]ข้อความ (50001) (SQLExecDirectW)")
    ฟังก์ชันนี้ดึงเฉพาะ "ข้อความ" ออกมา
    """
    text = str(exc)
    match = _MSG_RE.search(text)
    if match:
        msg = match.group(1).strip()
        if msg:
            return msg
    # fallback: เอาก้อนสุดท้ายหลัง [...] อันสุดท้าย
    chunks = re.split(r"\[[^\]]*\]", text)
    tail = chunks[-1].strip(" )'\"\n")
    return tail or "เกิดข้อผิดพลาดจากฐานข้อมูล"
