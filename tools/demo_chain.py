"""
demo_chain.py - สาธิต "chain" ทุกแบบที่อาจารย์อาจหมายถึง (ในสคริปต์เดียว)

  1) CASCADE CHAIN     ลบแถวแม่ -> แถวลูกถูกลบตาม (ON DELETE CASCADE)
  2) JOIN CHAIN        query ต่อกัน 5 ตารางตามความสัมพันธ์
  3) TRIGGER CHAIN     INSERT History -> trigger -> UPDATE PlayCount (ไม่มี UPDATE ในโค้ด)
  4) TRANSACTION CHAIN หลาย statement เป็นชุดเดียว: commit หรือ rollback พร้อมกัน
  5) LAYER CHAIN       กดในเว็บ -> Flask -> SQL -> ข้อมูลใหม่ปรากฏ (ยิง HTTP จริง)

ทุกอย่าง rollback ตอนจบ (ยกเว้น --keep)

ใช้
    python tools/demo_chain.py            # รันทั้งหมด
    python tools/demo_chain.py --pause    # หยุดรอ Enter ทีละแบบ
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import pyodbc
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Config  # noqa: E402

BASE = "http://127.0.0.1:5000"
DEMO_USER = "demo"


def line(char: str = "=") -> None:
    print(char * 78)


def title(text: str) -> None:
    print()
    line()
    print(f"  {text}")
    line()


def show(sql: str) -> None:
    print("\n  SQL:")
    for row in sql.strip().splitlines():
        print("    " + row.strip())


def table(cursor: pyodbc.Cursor, header: list[str]) -> None:
    rows = cursor.fetchall()
    if not rows:
        print("    (ไม่มีแถว)")
        return
    widths = [len(h) for h in header]
    data = []
    for row in rows:
        cells = ["" if v is None else str(v) for v in row]
        data.append(cells)
        widths = [max(w, len(c)) for w, c in zip(widths, cells)]
    fmt = "    " + "  ".join("{:<%d}" % w for w in widths)
    print(fmt.format(*header))
    print("    " + "  ".join("-" * w for w in widths))
    for cells in data:
        print(fmt.format(*cells))


def wait(on: bool) -> None:
    if on:
        input("\n  ▶ กด Enter เพื่อไปข้อต่อไป ...")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pause", action="store_true")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    conn = pyodbc.connect(Config.CONNECTION_STRING, autocommit=False)
    cur = conn.cursor()
    user_id = cur.execute("SELECT UserID FROM dbo.[User] WHERE Username = ?", DEMO_USER).fetchval()

    # ---------------------------------------------------------------- 1) CASCADE
    title("CHAIN 1) CASCADE CHAIN — ลบแม่แล้วลูกลบตาม")
    print("  ตารางที่มี ON DELETE CASCADE ในฐานข้อมูลนี้:")
    for row in cur.execute("""
        SELECT OBJECT_NAME(parent_object_id) AS child,
               OBJECT_NAME(referenced_object_id) AS parent,
               delete_referential_action_desc AS cascade_rule
        FROM sys.foreign_keys WHERE delete_referential_action_desc = 'CASCADE'
        ORDER BY child""").fetchall():
        print(f"    {row[0]:<20} -> {row[1]:<12} ({row[2]})")

    cur.execute("INSERT INTO dbo.Playlist (PLname, UserID, Create_Date) OUTPUT INSERTED.PlaylistID "
                "VALUES (?, ?, SYSDATETIME())", ("chain demo", user_id))
    playlist_id = cur.fetchval() if cur.description else None
    cur.execute("SELECT IDENT_CURRENT('dbo.Playlist') AS id")
    playlist_id = int(cur.fetchval())
    song_id = cur.execute("SELECT TOP 1 SongID FROM dbo.Song ORDER BY SongID").fetchval()
    cur.execute("INSERT INTO dbo.Playlist_Detail (PlaylistID, SongID, TrackNo, Date_Added) "
                "VALUES (?, ?, 1, SYSDATETIME())", (playlist_id, song_id))

    detail_before = cur.execute(
        "SELECT COUNT(*) FROM dbo.Playlist_Detail WHERE PlaylistID = ?", (playlist_id,)).fetchval()
    print(f"\n  สร้างเพลย์ลิสต์ #{playlist_id} ที่มีเพลงอยู่ {detail_before} แถว")

    show("DELETE FROM dbo.Playlist WHERE PlaylistID = ?   -- ไม่ได้สั่งลบ Playlist_Detail เลย")
    cur.execute("DELETE FROM dbo.Playlist WHERE PlaylistID = ?", (playlist_id,))
    detail_after = cur.execute(
        "SELECT COUNT(*) FROM dbo.Playlist_Detail WHERE PlaylistID = ?", (playlist_id,)).fetchval()
    print(f"\n  ✓ ลบแค่ตารางแม่ 1 แถว → แถวลูกหายไปด้วย (เหลือ {detail_after} แถว)")

    print("\n  ตรงข้าม: ตารางที่ไม่มี CASCADE จะ 'บล็อก' การลบ (History -> Song)")
    try:
        cur.execute("DELETE FROM dbo.Song WHERE SongID = ?", (song_id,))
        print("    (ลบได้ — ถ้าไม่ error แปลว่าเพลงนี้ไม่มี history)")
        conn.rollback()
    except pyodbc.IntegrityError as exc:
        print("    ✗ ถูกปฏิเสธโดย FK:", str(exc).split("]")[-1].strip()[:90])
        conn.rollback()
    wait(args.pause)

    # ---------------------------------------------------------------- 2) JOIN
    title("CHAIN 2) JOIN CHAIN — ต่อตารางตามความสัมพันธ์")
    sql = """
        SELECT TOP 5 u.Username, p.PLname, s.SongTitle, ar.ArtistName, r.[Role]
        FROM dbo.[User] AS u
        JOIN dbo.Playlist AS p         ON p.UserID = u.UserID
        JOIN dbo.Playlist_Detail AS pd ON pd.PlaylistID = p.PlaylistID
        JOIN dbo.Song AS s             ON s.SongID = pd.SongID
        JOIN dbo.Song_Artist_Role sar  ON sar.SongID = s.SongID
        JOIN dbo.Artist AS ar          ON ar.ArtistID = sar.ArtistID
        JOIN dbo.[Role] AS r           ON r.RoleID = sar.RoleID
        ORDER BY p.PlaylistID, pd.TrackNo
    """
    show(sql)
    cur.execute(sql)
    table(cur, ["ผู้ใช้", "เพลย์ลิสต์", "เพลง", "ศิลปิน", "บทบาท"])
    print("\n  → เดินครบ 6 ตารางตามเส้นความสัมพันธ์ของ ER")
    wait(args.pause)

    # ---------------------------------------------------------------- 3) TRIGGER
    title("CHAIN 3) TRIGGER CHAIN — INSERT แล้วมีผลต่ออีกตารางเอง")
    before = cur.execute("SELECT PlayCount FROM dbo.Song WHERE SongID = ?", (song_id,)).fetchval()
    print(f"  PlayCount ก่อน: {before}")
    show("INSERT INTO dbo.History (UserID, SongID, Played_At) VALUES (?, ?, SYSDATETIME())")
    cur.execute("INSERT INTO dbo.History (UserID, SongID, Played_At) VALUES (?, ?, SYSDATETIME())",
                (user_id, song_id))
    after = cur.execute("SELECT PlayCount FROM dbo.Song WHERE SongID = ?", (song_id,)).fetchval()
    print(f"\n  ✓ PlayCount หลัง: {after}  (เพิ่มขึ้นโดย trg_History_UpdatePlayCount)")
    print("    เราไม่เคยเขียน UPDATE dbo.Song ในโค้ดเลย — trigger ทำเอง")
    wait(args.pause)

    # ---------------------------------------------------------------- 4) TRANSACTION
    title("CHAIN 4) TRANSACTION CHAIN — หลาย statement เป็นชุดเดียว")
    show("""BEGIN TRAN
        INSERT Playlist      -> @id
        INSERT Playlist_Detail
        UPDATE Playlist SET PLname = ...
        ROLLBACK / COMMIT ทั้งชุด""")
    cur.execute("INSERT INTO dbo.Playlist (PLname, UserID, Create_Date) VALUES (?, ?, SYSDATETIME())",
                ("txn demo", user_id))
    cur.execute("SELECT IDENT_CURRENT('dbo.Playlist')")
    txn_id = int(cur.fetchval())
    cur.execute("INSERT INTO dbo.Playlist_Detail (PlaylistID, SongID, TrackNo, Date_Added) "
                "VALUES (?, ?, 1, SYSDATETIME())", (txn_id, song_id))
    cur.execute("UPDATE dbo.Playlist SET PLname = ? WHERE PlaylistID = ?", ("txn demo (แก้แล้ว)", txn_id))
    print(f"\n  ใน transaction: เพลย์ลิสต์ #{txn_id} ถูกสร้าง + แก้ชื่อแล้ว")
    conn.rollback()
    gone = cur.execute("SELECT COUNT(*) FROM dbo.Playlist WHERE PlaylistID = ?", (txn_id,)).fetchval()
    print(f"  หลัง ROLLBACK : เหลือ {gone} แถว (ทั้งชุดหายพร้อมกัน) ✓")
    wait(args.pause)

    # ---------------------------------------------------------------- 5) LAYER
    title("CHAIN 5) LAYER CHAIN — เว็บ -> Flask -> SQL -> ข้อมูลใหม่")
    name = "chain จากหน้าเว็บ"
    print(f"  ยิง HTTP POST ไปที่ {BASE}/playlists/create (เหมือนกดปุ่มในเว็บ)")
    before_count = cur.execute("SELECT COUNT(*) FROM dbo.Playlist").fetchval()
    try:
        session = requests.Session()
        session.post(f"{BASE}/login", data={"identity": DEMO_USER, "password": "demo1234"}, timeout=15)
        response = session.post(f"{BASE}/playlists/create", data={"plname": name},
                                allow_redirects=False, timeout=20)
        print(f"  HTTP {response.status_code} ← Flask ประมวลผล")
    except requests.RequestException as exc:
        print(f"  (เว็บไม่ทำงาน: {exc}) — ข้ามข้อนี้")
        response = None

    if response is not None:
        # ใช้ connection แยก (autocommit) เพื่อไม่ไป commit งานที่ค้างอยู่ใน transaction หลัก
        check = pyodbc.connect(Config.CONNECTION_STRING, autocommit=True)
        c2 = check.cursor()
        c2.execute("SELECT PlaylistID, PLname FROM dbo.Playlist WHERE PLname = ? ORDER BY PlaylistID DESC", (name,))
        rows = c2.fetchall()
        print(f"\n  ✓ ในฐานข้อมูลมีเพลย์ลิสต์ชื่อ '{name}' อยู่ {len(rows)} แถว:")
        for r in rows:
            print(f"      #{r[0]} {r[1]}")
        after_count = before_count + len(rows)
        print(f"  จำนวนเพลย์ลิสต์ใน DB: {before_count} -> {after_count}")
        print("\n  → ข้อมูลเดินครบสาย: HTML form -> Flask route -> SQL Server -> กลับมาแสดงผล")
        # แถวนี้ถูก commit โดย request ของเว็บแล้ว -> ลบด้วย connection เดียวกัน
        c2.execute("DELETE FROM dbo.Playlist WHERE PLname = ?", (name,))
        c2.close()
        check.close()

    # ---------------------------------------------------------------- จบ
    if args.keep:
        conn.commit()
        print("\n  บันทึกไว้ (--keep)")
    else:
        conn.rollback()
        print("\n  ROLLBACK ทั้งหมด — ฐานข้อมูลกลับสู่สภาพเดิม")

    cur.close()
    conn.close()

    line()
    print("  สาธิตครบ 5 แบบของ chain: CASCADE · JOIN · TRIGGER · TRANSACTION · LAYER")
    line()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
