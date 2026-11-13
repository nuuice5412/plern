"""
init_db.py - creates the MusicStreamingDB database on SQL Server Express

Runs 3 SQL scripts in order:
    01_schema.sql       -> creates DB + tables + constraints + indexes + trigger
    02_seed.sql         -> sample data
    03_views_procs.sql  -> views + stored procedures

Usage
    python tools/init_db.py                # create/reset the database
    python tools/init_db.py --check        # verify connectivity + count rows
    python tools/init_db.py --server "."   # target a different instance

Connection settings can be read from environment variables:
    MSSQL_SERVER   (default: .\\SQLEXPRESS)
    MSSQL_DATABASE (default: MusicStreamingDB)
    MSSQL_DRIVER   (default: ODBC Driver 18 for SQL Server)
    MSSQL_TRUSTED  (default: yes -> uses Windows Authentication)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

import pyodbc

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "db"

SERVER = os.environ.get("MSSQL_SERVER", r".\SQLEXPRESS")
DATABASE = os.environ.get("MSSQL_DATABASE", "MusicStreamingDB")
DRIVER = os.environ.get("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")

# SQL files to run in order (order matters: the trigger lives in schema so seed can use it)
SCRIPTS = ["01_schema.sql", "02_seed.sql", "03_views_procs.sql"]

# tables that must exist after a successful init
EXPECTED_TABLES = [
    "User",
    "Playlist",
    "Song",
    "Playlist_Detail",
    "History",
    "Artist",
    "Role",
    "Song_Artist_Role",
]


def connection_string(database: str | None = DATABASE) -> str:
    parts = [
        f"DRIVER={{{DRIVER}}}",
        f"SERVER={SERVER}",
        "Trusted_Connection=yes" if os.environ.get("MSSQL_TRUSTED", "yes") == "yes" else "",
        "TrustServerCertificate=yes",
        "Encrypt=yes",
        "APP=dsh-music-setup",
    ]
    if database:
        parts.insert(2, f"DATABASE={database}")
    return ";".join(p for p in parts if p) + ";"


def split_batches(sql: str) -> list[str]:
    """Split a .sql file into batches on GO keywords that sit on their own line."""
    batches, current = [], []
    for line in sql.splitlines():
        if re.fullmatch(r"\s*GO\s*(?:--.*)?", line, flags=re.IGNORECASE):
            batch = "\n".join(current).strip()
            if batch:
                batches.append(batch)
            current = []
        else:
            current.append(line)
    tail = "\n".join(current).strip()
    if tail:
        batches.append(tail)
    return batches


def run_script(cursor, path: pathlib.Path) -> None:
    sql = path.read_text(encoding="utf-8-sig")
    batches = split_batches(sql)
    print(f"  -> {path.name} ({len(batches)} batches)")
    for i, batch in enumerate(batches, start=1):
        try:
            cursor.execute(batch)
            # all result sets must be consumed before the next execute
            while cursor.nextset():
                pass
        except pyodbc.Error as exc:
            print(f"\n[ERROR] {path.name} batch #{i}:\n{exc}\n")
            print("--- batch ที่ผิด ---")
            print(batch[:1500])
            raise


def row_counts(cursor) -> list[tuple[str, int]]:
    rows = []
    for table in EXPECTED_TABLES:
        cursor.execute(f"SELECT COUNT(*) FROM dbo.[{table}]")
        rows.append((table, cursor.fetchone()[0]))
    return rows


def check() -> int:
    print(f"เชื่อมต่อ {SERVER} / {DATABASE} ...")
    with pyodbc.connect(connection_string(), timeout=10) as conn:
        cur = conn.cursor()
        cur.execute("SELECT @@VERSION")
        print("  " + cur.fetchone()[0].splitlines()[0].strip())
        cur.execute(
            "SELECT SUSER_SNAME(), IS_SRVROLEMEMBER('sysadmin'), DB_NAME()"
        )
        who, admin, db = cur.fetchone()
        print(f"  login={who}  sysadmin={admin}  database={db}")

        cur.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME"
        )
        tables = [r[0] for r in cur.fetchall()]
        print(f"  ตารางทั้งหมด ({len(tables)}): {', '.join(tables) or '-'}")

        missing = [t for t in EXPECTED_TABLES if t not in tables]
        if missing:
            print(f"\n[!] ยังขาดตาราง: {', '.join(missing)}")
            return 1

        print("\n--- จำนวนแถว ---")
        for name, n in row_counts(cur):
            print(f"  {name:<20} {n:>6}")

        cur.execute("SELECT TOP (5) SongTitle, PlayCount FROM dbo.vw_TopSongs")
        print("\n--- 5 เพลงยอดนิยม ---")
        for title, pc in cur.fetchall():
            print(f"  {title:<28} {pc:>4} plays")
    return 0


def init(force: bool) -> int:
    print(f"เป้าหมาย: {SERVER} / {DATABASE}")
    print(f"ไดรเวอร์: {DRIVER}\n")

    # 1) connect to master only; do not create the DB here, let 01_schema.sql do it
    try:
        conn = pyodbc.connect(connection_string(database="master"), timeout=15, autocommit=True)
    except pyodbc.Error as exc:
        print("[ERROR] เชื่อมต่อ SQL Server ไม่ได้")
        print(exc)
        print("\nตรวจสอบว่า service SQL Server ทำงานอยู่ และชื่อ instance ถูกต้อง")
        return 2

    with conn:
        cur = conn.cursor()
        cur.execute("SELECT @@VERSION")
        print("SQL Server:", cur.fetchone()[0].splitlines()[0].strip())
        cur.execute("SELECT IS_SRVROLEMEMBER('sysadmin')")
        if cur.fetchone()[0] != 1:
            print("[ERROR] login นี้ไม่มีสิทธิ์ sysadmin จึงสร้างฐานข้อมูลไม่ได้")
            return 2

        if force:
            # kill connections still attached to the target DB, then drop it for a clean restart
            cur.execute(
                f"""
                IF DB_ID(N'{DATABASE}') IS NOT NULL
                BEGIN
                    ALTER DATABASE [{DATABASE}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
                    DROP DATABASE [{DATABASE}];
                END
                """
            )
            print(f"เตรียมฐานข้อมูล {DATABASE} ใหม่ (drop ของเดิมถ้ามี)\n")

    # 2) run all schema/seed/views scripts on a single connection
    conn = pyodbc.connect(connection_string(database="master"), timeout=15, autocommit=True)
    with conn:
        cur = conn.cursor()
        for name in SCRIPTS:
            path = DB_DIR / name
            if not path.exists():
                print(f"[ERROR] ไม่พบไฟล์ {path}")
                return 3
            run_script(cur, path)

    print("\nสร้างฐานข้อมูลเรียบร้อย")
    return check()


def main() -> int:
    parser = argparse.ArgumentParser(description="สร้างฐานข้อมูล MusicStreamingDB")
    parser.add_argument("--check", action="store_true", help="ตรวจสถานะอย่างเดียว ไม่สร้างใหม่")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="ไม่ต้อง drop ฐานข้อมูลเดิม (01_schema.sql จะ drop แต่ตารางอยู่ดี)",
    )
    parser.add_argument("--server", help="ชื่อ instance เช่น .\\SQLEXPRESS")
    parser.add_argument(
        "--scripts",
        help="รันเฉพาะไฟล์ SQL ที่ระบุ เช่น 03 หรือ 03_views_procs.sql (ใช้ตอนแก้ view/proc โดยไม่ล้างข้อมูล)",
    )
    args = parser.parse_args()

    global SERVER
    if args.server:
        SERVER = args.server

    if args.scripts:
        return run_selected_scripts(args.scripts)

    if args.check:
        return check()
    return init(force=not args.keep)


def run_selected_scripts(spec: str) -> int:
    """Run the selected SQL files without dropping the database (for fixing views/procedures)."""
    wanted: list[pathlib.Path] = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if token.endswith(".sql"):
            wanted.append(DB_DIR / token)
        else:
            wanted.extend(sorted(DB_DIR.glob(f"{token.zfill(2)}_*.sql")))

    if not wanted:
        print(f"ไม่พบไฟล์ SQL ที่ตรงกับ: {spec}")
        return 3

    with pyodbc.connect(connection_string(), timeout=15, autocommit=True) as conn:
        cur = conn.cursor()
        for path in wanted:
            if not path.exists():
                print(f"[ERROR] ไม่พบไฟล์ {path}")
                return 3
            run_script(cur, path)

    print("เรียบร้อย")
    return check()


if __name__ == "__main__":
    sys.exit(main())


