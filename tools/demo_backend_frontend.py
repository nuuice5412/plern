"""
demo_backend_frontend.py - prove that the UI is driven by the backend/database.

"Change the backend and the frontend must follow" means: the pages must contain no
hard-coded data. Every value has to travel  SQL Server -> Flask route -> Jinja template.
This script demonstrates that in four steps and saves before/after screenshots.

    python tools/demo_backend_frontend.py

The web server must be running (python run.py). Every change is rolled back at the end.
"""
from __future__ import annotations

import base64
import pathlib
import re
import subprocess
import sys
import time
from tempfile import mkdtemp

import pyodbc
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Config  # noqa: E402

BASE = "http://127.0.0.1:5000"
SHOTS = ROOT / "docs" / "shots"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

OK = "  [OK]"
BAD = "  [!!]"


def conn():
    return pyodbc.connect(Config.CONNECTION_STRING, autocommit=True, timeout=10)


def shot(url: str, name: str) -> None:
    """Screenshot with headless Chrome (no extra dependencies)."""
    profile = mkdtemp(prefix="plern-shot-")
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--no-first-run", f"--user-data-dir={profile}",
         "--window-size=1440,900", f"--screenshot={SHOTS / name}", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
    )


def source_contains(needle: str) -> list[str]:
    """Where does this string appear in the source code? (should be nowhere)"""
    hits = []
    patterns = ("app/templates/*.html", "app/*.py", "app/static/js/*.js")
    for pattern in patterns:
        for path in ROOT.glob(pattern):
            if needle in path.read_text(encoding="utf-8-sig", errors="ignore"):
                hits.append(str(path.relative_to(ROOT)))
    return hits


def main() -> int:
    problems = 0
    SHOTS.mkdir(parents=True, exist_ok=True)

    try:
        requests.get(BASE + "/", timeout=10)
    except requests.RequestException:
        print(f"{BAD} เปิดเว็บที่ {BASE} ไม่ได้ — รัน `python run.py` ก่อน")
        return 2

    with conn() as db:
        cur = db.cursor()
        cur.execute("SELECT TOP 1 SongID, SongTitle, PlayCount FROM dbo.Song ORDER BY SongID")
        song_id, original, plays = cur.fetchone()
        # a role name we will edit to prove the JSON API also reads the DB
        cur.execute("SELECT TOP 1 RoleID, [Role] FROM dbo.[Role] ORDER BY RoleID")
        role_id, original_role = cur.fetchone()

        print("=" * 74)
        print(" DEMO: SQL Server  ->  Flask (backend)  ->  page (frontend)")
        print("=" * 74)
        print(f"\nเพลงที่ใช้ทดสอบ: SongID={song_id}  {original!r}  (เล่น {plays} ครั้ง)")

        # ------------------------------------------------------------------
        print("\n[1] พิสูจน์ว่าไม่มีข้อมูล hardcode อยู่ในโค้ด")
        print(f"    ค้นคำว่า {original!r} ในไฟล์ .html / .py / .js ทั้งโปรเจกต์")
        hits = source_contains(original)
        if hits:
            print(f"{BAD} พบในโค้ด: {hits}")
            problems += 1
        else:
            print(f"{OK} ไม่พบในโค้ดเลย -> ค่าที่เห็นบนหน้าจอต้องมาจากฐานข้อมูลเท่านั้น")

        # ------------------------------------------------------------------
        print("\n[2] หน้าเว็บแสดงค่าที่ตรงกับในฐานข้อมูล")
        page = requests.get(f"{BASE}/song/{song_id}", timeout=15).text
        if original in page:
            print(f"{OK} หน้า /song/{song_id} มี {original!r} ตรงกับ SELECT ใน DB")
        else:
            print(f"{BAD} หน้าเว็บไม่แสดงชื่อนี้")
            problems += 1
        shot(f"{BASE}/song/{song_id}", "demo_before.png")

        # ------------------------------------------------------------------
        print("\n[3] แก้ข้อมูลใน DB (จำลองการแก้จาก SSMS) แล้วดูหน้าเว็บ")
        marker = original + " ★"
        print(f"    UPDATE dbo.Song SET SongTitle = N'{marker}' WHERE SongID = {song_id};")
        cur.execute("UPDATE dbo.Song SET SongTitle = ? WHERE SongID = ?", marker, song_id)

        page = requests.get(f"{BASE}/song/{song_id}", timeout=15).text
        if marker in page:
            print(f"{OK} เปิดหน้าใหม่ -> เห็น {marker!r} ทันที (ไม่ต้องรีสตาร์ตเซิร์ฟเวอร์)")
        else:
            print(f"{BAD} หน้าเว็บยังไม่เปลี่ยน")
            problems += 1
        shot(f"{BASE}/song/{song_id}", "demo_after.png")

        # ------------------------------------------------------------------
        print("\n[4] backend (JSON API) ก็อ่านจาก DB เช่นกัน — แก้ชื่อบทบาทใน DB")
        before_api = requests.get(f"{BASE}/api/song/{song_id}", timeout=15).json()
        before_roles = {c["Role"] for c in before_api.get("credits", [])}

        new_role = original_role + " (edited)"
        cur.execute("UPDATE dbo.[Role] SET [Role] = ? WHERE RoleID = ?", new_role, role_id)
        after_api = requests.get(f"{BASE}/api/song/{song_id}", timeout=15).json()
        after_roles = {c["Role"] for c in after_api.get("credits", [])}

        print(f"    บทบาทใน API ก่อนแก้: {sorted(before_roles)}")
        print(f"    บทบาทใน API หลังแก้: {sorted(after_roles)}")
        if original_role in before_roles and new_role in after_roles:
            print(f"{OK} API ที่หน้า player เรียก ก็สะท้อนการแก้ใน DB")
        else:
            print(f"{BAD} API ไม่สะท้อนการแก้ (เพลงนี้อาจไม่มีบทบาทนี้)")
            problems += 1

        # ------------------------------------------------------------------
        print("\n[5] ทดสอบ trigger: บันทึกการฟัง 1 ครั้ง -> PlayCount เพิ่ม -> หน้าเว็บเห็นยอดใหม่")
        cur.execute("SELECT ISNULL(MAX(HistoryID), 0) FROM dbo.History")
        last_id = cur.fetchone()[0]
        cur.execute("INSERT INTO dbo.History (UserID, SongID) VALUES (1, ?)", song_id)
        cur.execute("SELECT PlayCount FROM dbo.Song WHERE SongID = ?", (song_id,))
        new_plays = cur.fetchone()[0]
        page = requests.get(f"{BASE}/song/{song_id}", timeout=15).text
        print(f"    PlayCount: {plays} -> {new_plays}")
        if new_plays == plays + 1 and f"{new_plays} ครั้งที่เล่น" in page:
            print(f"{OK} trigger บวกยอดให้เอง และหน้าเว็บแสดง {new_plays} ครั้งที่เล่น")
        else:
            print(f"{BAD} ยอดไม่ตรงกัน")
            problems += 1

        # ------------------------------------------------------------------
        print("\n[6] คืนค่าทุกอย่าง")
        cur.execute("UPDATE dbo.Song SET SongTitle = ?, PlayCount = ? WHERE SongID = ?",
                    original, plays, song_id)
        cur.execute("UPDATE dbo.[Role] SET [Role] = ? WHERE RoleID = ?", original_role, role_id)
        cur.execute("DELETE FROM dbo.History WHERE HistoryID > ?", last_id)
        cur.execute("SELECT SongTitle, PlayCount FROM dbo.Song WHERE SongID = ?", (song_id,))
        back = cur.fetchone()
        if back[0] == original and back[1] == plays:
            print(f"{OK} ข้อมูลกลับเป็นเดิม ({original!r}, {plays} ครั้ง)")
        else:
            print(f"{BAD} คืนค่าไม่ครบ: {back}")
            problems += 1

    print("\n" + "=" * 74)
    if problems == 0:
        print(" สรุป: หน้าเว็บไม่มีข้อมูล hardcode — ทุกค่ามาจาก SQL Server ผ่าน Flask")
        print(f" ภาพก่อน/หลังแก้อยู่ที่ docs/shots/demo_before.png, demo_after.png")
    else:
        print(f" พบปัญหา {problems} จุด")
    print("=" * 74)
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
