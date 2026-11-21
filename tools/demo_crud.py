"""
demo_crud.py - สาธิต 5 ขั้นที่อาจารย์ขอ ตามตัวอย่างรายงาน SmartParking

    CONNECT -> SELECT -> INSERT -> UPDATE -> DELETE
    (+ ของแถม: VIEW, TRIGGER, STORED PROCEDURE, TRANSACTION)

ทุกขั้นพิมพ์ SQL จริงที่รัน + ผลลัพธ์ + จำนวนแถวที่โดน
ตอนจบจะ rollback ทุกอย่างกลับเหมือนเดิม (ไม่ทิ้งขยะในฐานข้อมูล)

ใช้
    python tools/demo_crud.py            # รันทั้งหมดรวด
    python tools/demo_crud.py --pause    # หยุดรอ Enter ทีละขั้น (สำหรับพรีเซนต์)
    python tools/demo_crud.py --keep     # ไม่ rollback (ให้เห็นผลค้างในเว็บ)
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import pyodbc

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Config  # noqa: E402

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
        cells = ["" if value is None else str(value) for value in row]
        data.append(cells)
        widths = [max(w, len(c)) for w, c in zip(widths, cells)]
    fmt = "    " + "  ".join("{:<%d}" % w for w in widths)
    print(fmt.format(*header))
    print("    " + "  ".join("-" * w for w in widths))
    for cells in data:
        print(fmt.format(*cells))


def wait(enabled: bool, message: str = "กด Enter เพื่อไปขั้นต่อไป") -> None:
    if enabled:
        input(f"\n  ▶ {message} ...")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pause", action="store_true", help="หยุดรอ Enter ทีละขั้น")
    parser.add_argument("--keep", action="store_true", help="ไม่ rollback ตอนจบ")
    args = parser.parse_args()

    conn = pyodbc.connect(Config.CONNECTION_STRING, autocommit=False)
    cursor = conn.cursor()

    # ------------------------------------------------------------------ CONNECT
    title("1) CONNECT — เชื่อมต่อฐานข้อมูล")
    info = conn.getinfo(pyodbc.SQL_DBMS_NAME), conn.getinfo(pyodbc.SQL_DBMS_VER)
    print(f"  DBMS      : {info[0]} {info[1]}")
    print(f"  Database  : {cursor.execute('SELECT DB_NAME()').fetchval()}")
    print(f"  Server    : {cursor.execute('SELECT @@SERVERNAME').fetchval()}")
    print(f"  User      : {cursor.execute('SELECT SUSER_SNAME()').fetchval()}")
    table_count = cursor.execute(
        "SELECT COUNT(*) FROM sys.tables WHERE schema_id = SCHEMA_ID('dbo')").fetchval()
    print(f"  Tables    : {table_count}")
    wait(args.pause)

    user_id = cursor.execute(
        "SELECT UserID FROM dbo.[User] WHERE Username = ?", DEMO_USER).fetchval()
    print(f"\n  ผู้ใช้ที่ใช้สาธิต: {DEMO_USER} (UserID = {user_id})")

    # ------------------------------------------------------------------ SELECT
    title("2) SELECT — อ่านข้อมูล (JOIN หลายตาราง)")
    sql = """
        SELECT TOP 5 s.SongID, s.SongTitle, a.ArtistName, s.PlayCount
        FROM dbo.Song AS s
        JOIN dbo.Song_Artist_Role AS sar ON sar.SongID = s.SongID
        JOIN dbo.Artist AS a            ON a.ArtistID = sar.ArtistID
        JOIN dbo.[Role] AS r            ON r.RoleID = sar.RoleID
        WHERE r.[Role] = N'Singer'
        ORDER BY s.PlayCount DESC
    """
    show(sql)
    cursor.execute(sql)
    table(cursor, ["SongID", "ชื่อเพลง", "ศิลปิน", "ยอดฟัง"])

    print("\n  อ่านผ่าน VIEW ที่สร้างไว้ (vw_PlaylistSummary):")
    sql_view = "SELECT TOP 3 PlaylistID, PLname, Song_Amount, Total_Time_Text FROM dbo.vw_PlaylistSummary ORDER BY Song_Amount DESC"
    show(sql_view)
    cursor.execute(sql_view)
    table(cursor, ["PlaylistID", "ชื่อเพลย์ลิสต์", "จำนวนเพลง", "ความยาว"])
    wait(args.pause)

    # ------------------------------------------------------------------ INSERT
    title("3) INSERT — เพิ่มข้อมูล")
    name = "เพลย์ลิสต์สาธิต (INSERT)"
    sql_insert = """
        INSERT INTO dbo.Playlist (PLname, UserID, Create_Date)
        OUTPUT INSERTED.PlaylistID
        VALUES (?, ?, SYSDATETIME())
    """
    show(sql_insert)
    playlist_id = cursor.execute(sql_insert, (name, user_id)).fetchval()
    print(f"\n  ✓ สร้างเพลย์ลิสต์ใหม่ PlaylistID = {playlist_id}")

    song_id = cursor.execute("SELECT TOP 1 SongID FROM dbo.Song ORDER BY SongID").fetchval()
    sql_detail = """
        INSERT INTO dbo.Playlist_Detail (PlaylistID, SongID, TrackNo, Date_Added)
        VALUES (?, ?, ?, SYSDATETIME())
    """
    show(sql_detail)
    cursor.execute(sql_detail, (playlist_id, song_id, 1))
    print(f"  ✓ เพิ่มเพลง SongID = {song_id} เข้าเพลย์ลิสต์ (1 แถว)")

    print("\n  ตรวจผลหลัง INSERT:")
    cursor.execute("""
        SELECT pd.PlaylistID, pd.SongID, s.SongTitle, pd.TrackNo
        FROM dbo.Playlist_Detail AS pd
        JOIN dbo.Song AS s ON s.SongID = pd.SongID
        WHERE pd.PlaylistID = ?
    """, (playlist_id,))
    table(cursor, ["PlaylistID", "SongID", "ชื่อเพลง", "ลำดับ"])
    wait(args.pause)

    # ------------------------------------------------------------------ UPDATE
    title("4) UPDATE — แก้ไขข้อมูล")
    before = cursor.execute(
        "SELECT PLname FROM dbo.Playlist WHERE PlaylistID = ?", playlist_id).fetchval()
    print(f"  ชื่อก่อนแก้: {before}")

    sql_update = "UPDATE dbo.Playlist SET PLname = ? WHERE PlaylistID = ?"
    show(sql_update)
    affected = cursor.execute(sql_update, ("เพลย์ลิสต์สาธิต (UPDATE แล้ว)", playlist_id)).rowcount
    after = cursor.execute(
        "SELECT PLname FROM dbo.Playlist WHERE PlaylistID = ?", playlist_id).fetchval()
    print(f"\n  ✓ แก้ 1 แถว (rowcount = {affected})")
    print(f"  ชื่อหลังแก้: {after}")
    wait(args.pause)

    # ------------------------------------------------------------------ DELETE
    title("5) DELETE — ลบข้อมูล")
    sql_delete_detail = "DELETE FROM dbo.Playlist_Detail WHERE PlaylistID = ?"
    show(sql_delete_detail)
    print(f"  ✓ ลบเพลงในเพลย์ลิสต์ {cursor.execute(sql_delete_detail, (playlist_id,)).rowcount} แถว")

    sql_delete = "DELETE FROM dbo.Playlist WHERE PlaylistID = ?"
    show(sql_delete)
    print(f"  ✓ ลบเพลย์ลิสต์ {cursor.execute(sql_delete, (playlist_id,)).rowcount} แถว")

    left = cursor.execute(
        "SELECT COUNT(*) FROM dbo.Playlist WHERE PlaylistID = ?", playlist_id).fetchval()
    print(f"\n  ตรวจผล: เหลือเพลย์ลิสต์หมายเลขนี้อยู่ {left} แถว (ควรเป็น 0)")
    wait(args.pause)

    # ------------------------------------------------------------------ โบนัส
    title("โบนัส 1) TRIGGER — นับยอดฟังอัตโนมัติ")
    before_plays = cursor.execute(
        "SELECT PlayCount FROM dbo.Song WHERE SongID = ?", song_id).fetchval()
    print(f"  ยอดฟังก่อน: {before_plays}")
    show("INSERT INTO dbo.History (UserID, SongID, Played_At) VALUES (?, ?, SYSDATETIME())")
    cursor.execute(
        "INSERT INTO dbo.History (UserID, SongID, Played_At) VALUES (?, ?, SYSDATETIME())",
        (user_id, song_id))
    after_plays = cursor.execute(
        "SELECT PlayCount FROM dbo.Song WHERE SongID = ?", song_id).fetchval()
    print(f"  ✓ INSERT ลง History 1 แถว → trigger เพิ่ม PlayCount เป็น {after_plays} (ไม่มี UPDATE ในโค้ด)")

    title("โบนัส 2) STORED PROCEDURE")
    procs = [row[0] for row in cursor.execute(
        "SELECT name FROM sys.procedures ORDER BY name").fetchall()]
    print("  procedure ที่มี:", ", ".join(procs) or "-")
    print("  ลองเรียก usp_Playlist_Create (มี OUTPUT parameter ด้วย):")
    show("""DECLARE @new INT;
    EXEC dbo.usp_Playlist_Create @UserID = ?, @PLname = ?, @NewPlaylistID = @new OUTPUT;
    SELECT @new AS NewPlaylistID;""")
    created = cursor.execute(
        """DECLARE @new INT;
           EXEC dbo.usp_Playlist_Create @UserID = ?, @PLname = ?, @NewPlaylistID = @new OUTPUT;
           SELECT @new AS NewPlaylistID;""",
        (user_id, "เพลย์ลิสต์จาก PROCEDURE")).fetchval()
    print(f"  ✓ procedure สร้าง PlaylistID = {created}")
    cursor.execute("SELECT PlaylistID, PLname FROM dbo.Playlist WHERE PlaylistID = ?", created)
    table(cursor, ["PlaylistID", "ชื่อเพลย์ลิสต์"])
    cursor.execute("DELETE FROM dbo.Playlist WHERE PlaylistID = ?", created)

    title("โบนัส 3) TRANSACTION — ยกเลิกได้")
    show("BEGIN TRANSACTION ... UPDATE ... ROLLBACK")
    cursor.execute("UPDATE dbo.Song SET PlayCount = PlayCount + 1000 WHERE SongID = ?", song_id)
    inside = cursor.execute("SELECT PlayCount FROM dbo.Song WHERE SongID = ?", song_id).fetchval()
    print(f"  ใน transaction: {inside}  (บวกไป 1000)")
    cursor.rollback()
    outside = cursor.execute("SELECT PlayCount FROM dbo.Song WHERE SongID = ?", song_id).fetchval()
    print(f"  หลัง ROLLBACK : {outside}  → กลับค่าเดิม ✓")

    # ------------------------------------------------------------------ จบ
    if args.keep:
        conn.commit()
        print("\n  บันทึกการเปลี่ยนแปลงไว้ (--keep)")
    else:
        conn.rollback()
        print("\n  ROLLBACK ทั้งหมด — ฐานข้อมูลกลับสู่สภาพเดิม")

    cursor.close()
    conn.close()

    line()
    print("  สาธิตครบ 5 ขั้น: CONNECT → SELECT → INSERT → UPDATE → DELETE")
    print("  + VIEW, TRIGGER, STORED PROCEDURE, TRANSACTION")
    line()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
