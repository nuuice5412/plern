"""
รวมศิลปินที่ถูกแยกผิด: "Whal" + "Dolph" -> "Whal & Dolph"

สาเหตุ: iTunes ส่ง artistName มาเป็น "Whal & Dolph" แต่ split_artists() แยกที่ "&"
ทำให้เกิดศิลปินเดี่ยวปลอม 2 คน (Whal, Dolph) และบทบาทในเพลงผิด
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import create_app, db  # noqa: E402

DUO_NAME = "Whal & Dolph"
SPLIT_NAMES = ("Whal", "Dolph")

app = create_app()
with app.app_context():
    duo = db.query_one("SELECT ArtistID FROM dbo.Artist WHERE ArtistName = ?", (DUO_NAME,))
    if not duo:
        print("ไม่พบศิลปินคู่")
        raise SystemExit(1)
    duo_id = duo["ArtistID"]

    roles = {r["Role"]: r["RoleID"] for r in db.query("SELECT RoleID, [Role] FROM dbo.[Role]")}
    singer_id = roles["Singer"]

    ids = [r["ArtistID"] for r in db.query(
        "SELECT ArtistID FROM dbo.Artist WHERE ArtistName IN (?, ?)", SPLIT_NAMES)]
    print("ศิลปินที่แยกผิด:", ids, "-> รวมเข้า", duo_id)

    if not ids:
        print("ไม่มีอะไรต้องแก้")
        raise SystemExit(0)

    placeholders = ",".join("?" * len(ids))
    songs = db.query(
        f"SELECT DISTINCT SongID FROM dbo.Song_Artist_Role WHERE ArtistID IN ({placeholders})", tuple(ids))
    print("เพลงที่ได้รับผลกระทบ:", len(songs))

    added = 0
    for row in songs:
        song_id = row["SongID"]
        exists = db.query_one(
            "SELECT 1 AS x FROM dbo.Song_Artist_Role WHERE SongID = ? AND ArtistID = ? AND RoleID = ?",
            (song_id, duo_id, singer_id))
        if not exists:
            db.execute(
                "INSERT INTO dbo.Song_Artist_Role (SongID, ArtistID, RoleID) VALUES (?, ?, ?)",
                (song_id, duo_id, singer_id))
            added += 1

    # บทบาทของศิลปินเดี่ยวที่เหลือ (Composer/Producer) ย้ายมาเป็นของคู่
    for row in db.query(
            f"SELECT SongID, RoleID FROM dbo.Song_Artist_Role WHERE ArtistID IN ({placeholders}) "
            f"AND RoleID <> ?", tuple(ids) + (singer_id,)):
        exists = db.query_one(
            "SELECT 1 AS x FROM dbo.Song_Artist_Role WHERE SongID = ? AND ArtistID = ? AND RoleID = ?",
            (row["SongID"], duo_id, row["RoleID"]))
        if not exists:
            db.execute(
                "INSERT INTO dbo.Song_Artist_Role (SongID, ArtistID, RoleID) VALUES (?, ?, ?)",
                (row["SongID"], duo_id, row["RoleID"]))

    db.execute(f"DELETE FROM dbo.Song_Artist_Role WHERE ArtistID IN ({placeholders})", tuple(ids))
    db.execute(f"DELETE FROM dbo.Artist WHERE ArtistID IN ({placeholders})", tuple(ids))
    print(f"เพิ่มบทบาท Singer ให้คู่ {added} แถว · ลบศิลปินเดี่ยวแล้ว")

    left = db.query(
        f"SELECT COUNT(*) AS n FROM dbo.Song_Artist_Role WHERE ArtistID IN ({placeholders})", tuple(ids))
    print("แถวที่ยังอ้างถึงศิลปินที่ลบ:", left[0]["n"] if left else 0)
    total = db.query_one("SELECT COUNT(*) AS n FROM dbo.Artist")["n"]
    print("ศิลปินคงเหลือ:", total)
