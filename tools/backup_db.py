"""
backup_db.py - สำรอง/กู้คืนฐานข้อมูล MusicStreamingDB ด้วย BACKUP DATABASE ของ SQL Server

ใช้
    python tools/backup_db.py                 # สำรอง -> backups/MusicStreamingDB_<เวลา>.bak
    python tools/backup_db.py --list          # ดูไฟล์สำรองที่มี
    python tools/backup_db.py --restore FILE  # กู้คืนจากไฟล์ (ถามยืนยัน)

ไฟล์ .bak เก็บที่ backups/ ซึ่งอยู่ใน .gitignore (ไม่ขึ้น GitHub)
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import shutil
import sys

import pyodbc

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Config  # noqa: E402

DATABASE = "MusicStreamingDB"
BACKUP_DIR = ROOT / "backups"


def server_connection(database: str | None = DATABASE) -> pyodbc.Connection:
    """ต่อแบบไม่ระบุฐานข้อมูล (สำหรับ BACKUP/RESTORE)"""
    base = Config.CONNECTION_STRING
    if "DATABASE=" in base.upper():
        parts = []
        for chunk in base.split(";"):
            if chunk.upper().startswith("DATABASE="):
                continue
            parts.append(chunk)
        base = ";".join(parts)
    if database:
        base += f";DATABASE={database}"
    return pyodbc.connect(base, autocommit=True)


def server_backup_dir(conn: pyodbc.Connection) -> pathlib.Path:
    """โฟลเดอร์ที่บัญชีบริการของ SQL Server เขียนได้ (Documents ของผู้ใช้เขียนไม่ได้)"""
    row = conn.execute("SELECT SERVERPROPERTY('InstanceDefaultBackupPath') AS p").fetchone()
    path = pathlib.Path(row[0])
    path.mkdir(parents=True, exist_ok=True)
    return path


def do_backup() -> int:
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{DATABASE}_{stamp}.bak"

    with server_connection() as conn:
        staging = server_backup_dir(conn) / name
        conn.execute(f"BACKUP DATABASE [{DATABASE}] TO DISK = ? WITH INIT",
                     (str(staging),))

    target = BACKUP_DIR / name
    shutil.copy2(staging, target)
    staging.unlink(missing_ok=True)

    size = target.stat().st_size / 1024 / 1024
    print(f"สำรองแล้ว: {target}  ({size:.1f} MB)")
    return 0


def do_restore(path: pathlib.Path) -> int:
    if not path.exists():
        print(f"ไม่พบไฟล์: {path}")
        return 1

    answer = input(f"กู้คืนทับฐานข้อมูล {DATABASE} ด้วย {path.name}? พิมพ์ yes: ").strip().lower()
    if answer != "yes":
        print("ยกเลิก")
        return 1

    with server_connection(database=None) as conn:
        staging = server_backup_dir(conn) / path.name
        shutil.copy2(path, staging)
        conn.execute(f"ALTER DATABASE [{DATABASE}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
        try:
            conn.execute(f"RESTORE DATABASE [{DATABASE}] FROM DISK = ? WITH REPLACE", (str(staging),))
        finally:
            conn.execute(f"ALTER DATABASE [{DATABASE}] SET MULTI_USER")
        staging.unlink(missing_ok=True)
    print("กู้คืนเรียบร้อย")
    return 0


def do_list() -> int:
    if not BACKUP_DIR.exists():
        print("ยังไม่มีไฟล์สำรอง")
        return 0
    files = sorted(BACKUP_DIR.glob("*.bak"))
    if not files:
        print("ยังไม่มีไฟล์สำรอง")
        return 0
    for f in files:
        print(f"{f.name:<44} {f.stat().st_size / 1024 / 1024:>8.1f} MB")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="สำรอง/กู้คืนฐานข้อมูล Plern")
    parser.add_argument("--restore", metavar="FILE", help="กู้คืนจากไฟล์ .bak")
    parser.add_argument("--list", action="store_true", help="แสดงไฟล์สำรอง")
    args = parser.parse_args()

    if args.list:
        return do_list()
    if args.restore:
        return do_restore(pathlib.Path(args.restore))
    return do_backup()


if __name__ == "__main__":
    raise SystemExit(main())
