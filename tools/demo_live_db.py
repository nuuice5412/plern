"""
demo_live_db.py - prove the frontend is wired to the real database (not hardcoded data)

This script will
  1. read values from the database
  2. change data with raw SQL (bypassing the app)
  3. load the web page and check the new value is visible immediately
  4. restore the original value
  5. test the trigger: add a play history row -> PlayCount goes up -> the page shows the new count

For demoing to the instructor (the web app must be running at http://127.0.0.1:5000)

    python tools/demo_live_db.py
    python tools/demo_live_db.py --base http://127.0.0.1:5000 --song 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyodbc
import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Config  # noqa: E402

OK = "  [OK]"
FAIL = "  [!!]"


def conn():
    return pyodbc.connect(Config.CONNECTION_STRING, autocommit=True, timeout=10)


def fetch(url: str) -> requests.Response:
    return requests.get(url, timeout=15)


def main() -> int:
    parser = argparse.ArgumentParser(description="สาธิตว่าเว็บอ่านข้อมูลจาก SQL Server จริง")
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    parser.add_argument("--song", type=int, default=1)
    args = parser.parse_args()

    base = args.base.rstrip("/")
    song_id = args.song
    problems = 0

    print("=" * 70)
    print(" สาธิต: ฐานข้อมูล SQL Server  <->  Flask backend  <->  หน้าเว็บ")
    print("=" * 70)

    try:
        fetch(base + "/")
    except requests.RequestException as exc:
        print(f"{FAIL} เปิดเว็บที่ {base} ไม่ได้ — รัน `python run.py` ก่อน")
        print(f"       ({exc})")
        return 2

    with conn() as db:
        cur = db.cursor()
        cur.execute("SELECT SongTitle, PlayCount FROM dbo.Song WHERE SongID = ?", song_id)
        row = cur.fetchone()
        if row is None:
            print(f"{FAIL} ไม่พบเพลง SongID={song_id}")
            return 2
        original_title, play_count = row[0], row[1]

        # ------------------------------------------------------------------
        print(f"\n1) ค่าในฐานข้อมูลตอนนี้ (SongID={song_id})")
        print(f"   SongTitle = {original_title}")
        print(f"   PlayCount = {play_count}")

        page = fetch(f"{base}/song/{song_id}").text
        if original_title in page:
            print(f"{OK} หน้าเว็บ /song/{song_id} แสดงชื่อเพลงนี้ (ดึงมาจาก DB ไม่ใช่ hardcode)")
        else:
            print(f"{FAIL} หน้าเว็บไม่พบชื่อเพลงนี้")
            problems += 1

        # ------------------------------------------------------------------
        marker = original_title + " · แก้จาก SQL"
        print("\n2) แก้ข้อมูลด้วย SQL ตรง ๆ (UPDATE จากสคริปต์นี้ ไม่ผ่านตัวแอป)")
        print(f"   UPDATE dbo.Song SET SongTitle = N'{marker}' WHERE SongID = {song_id};")
        cur.execute("UPDATE dbo.Song SET SongTitle = ? WHERE SongID = ?", marker, song_id)

        page = fetch(f"{base}/song/{song_id}").text
        if marker in page:
            print(f"{OK} เปิดหน้าเว็บใหม่ -> เห็นชื่อที่เพิ่งแก้ทันที (ไม่ต้องรีสตาร์ตเซิร์ฟเวอร์)")
        else:
            print(f"{FAIL} หน้าเว็บยังไม่เปลี่ยน")
            problems += 1

        # ------------------------------------------------------------------
        print("\n3) คืนชื่อเพลงเดิม")
        cur.execute("UPDATE dbo.Song SET SongTitle = ? WHERE SongID = ?",
                    original_title, song_id)
        page = fetch(f"{base}/song/{song_id}").text
        if original_title in page and marker not in page:
            print(f"{OK} กลับมาเป็นชื่อเดิมแล้ว")
        else:
            print(f"{FAIL} คืนค่าไม่สำเร็จ")
            problems += 1

        # ------------------------------------------------------------------
        print("\n4) ทดสอบ TRIGGER: เพิ่มประวัติการฟัง 1 แถว")
        print("   INSERT INTO dbo.History (UserID, SongID) VALUES (1, ?);")
        cur.execute("SELECT ISNULL(MAX(HistoryID), 0) FROM dbo.History")
        before_max = cur.fetchone()[0]
        cur.execute("INSERT INTO dbo.History (UserID, SongID) VALUES (1, ?)", song_id)
        cur.execute("SELECT PlayCount FROM dbo.Song WHERE SongID = ?", song_id)
        after = cur.fetchone()[0]
        print(f"   PlayCount: {play_count} -> {after}")

        payload = requests.get(f"{base}/api/song/{song_id}", timeout=15).json()
        if after == play_count + 1 and payload.get("plays") == after:
            print(f"{OK} trigger บวกยอดให้เอง และ API ของเว็บคืนยอดใหม่ตรงกัน")
        else:
            print(f"{FAIL} ยอดไม่ตรง (db={after}, api={payload.get('plays')})")
            problems += 1

        page = fetch(f"{base}/song/{song_id}").text
        if f"{after} ครั้งที่เล่น" in page:
            print(f"{OK} หน้าเว็บแสดงยอดใหม่ {{after}} ครั้งที่เล่น".replace("{after}", str(after)))
        else:
            print(f"{FAIL} หน้าเว็บไม่แสดงยอดใหม่")
            problems += 1

        # ------------------------------------------------------------------
        print("\n5) คืนสภาพข้อมูล (ลบแถวทดสอบ + ลดยอดกลับ)")
        cur.execute("DELETE FROM dbo.History WHERE HistoryID > ?", before_max)
        cur.execute("UPDATE dbo.Song SET PlayCount = ? WHERE SongID = ?", play_count, song_id)
        cur.execute("SELECT SongTitle, PlayCount FROM dbo.Song WHERE SongID = ?", song_id)
        back = cur.fetchone()
        if back[0] == original_title and back[1] == play_count:
            print(f"{OK} ข้อมูลกลับเป็นเดิม (PlayCount = {play_count})")
        else:
            print(f"{FAIL} คืนค่าไม่ครบ: {back}")
            problems += 1

    print("\n" + "=" * 70)
    if problems == 0:
        print(" สรุป: หน้าเว็บอ่าน/เขียนข้อมูลผ่านฐานข้อมูลจริงทั้งหมด")
        print("       แก้ข้อมูลใน SQL Server -> หน้าเว็บเปลี่ยนทันที")
    else:
        print(f" พบปัญหา {problems} จุด")
    print("=" * 70)
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
