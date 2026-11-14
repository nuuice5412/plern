"""
เก็บกวาดข้อมูลศิลปิน/เพลง หลังขยายคลังเป็น 787 เพลง

  1) แยกศิลปินที่ชื่อเป็น "การฟีเจอริ่ง" (Lipta & fellow fellow -> Lipta + fellow fellow)
  2) รวมศิลปินที่ชื่อซ้ำ (ปาล์มมี่ อีฟ ปานเจริญ -> Palmy)
  3) ลบเพลงซ้ำ (ชื่อเดียวกัน ศิลปินเดียวกัน) โดยย้าย History / Playlist_Detail ไปเพลงที่เก็บไว้

ใช้:  python tools/cleanup_catalog.py [--apply]
      ไม่ใส่ --apply = ดูเฉย ๆ (dry run)
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import create_app, db  # noqa: E402

# ชื่อที่ต้องแยก (ศิลปินร่วมงาน ไม่ใช่วง)
COLLABS = [
    "Lipta & fellow fellow",
    "Tilly Birds & Safeplanet",
    "DICEBLUE & DICE",
    "YOUNGOHM & KT KRATAE",
    "PP KRIT & Girly Berry",
    "SEA. & SARAN",
    "BILLKIN & Ink Waruntorn",
    "fellow fellow & PUN",
]

# ชื่อซ้ำที่ต้องรวมเข้า -> ชื่อเดิม
ALIASES = {
    "ปาล์มมี่ อีฟ ปานเจริญ": "Palmy",
}


def apply_or_print(sql: str, params: tuple, apply: bool) -> None:
    print(("  SQL: " + sql.strip().splitlines()[0][:100]))
    if apply:
        db.execute(sql, params)


def main() -> int:
    apply = "--apply" in sys.argv

    app = create_app()
    with app.app_context():
        roles = {r["Role"]: r["RoleID"] for r in db.query("SELECT RoleID, [Role] FROM dbo.[Role]")}
        singer, featured = roles["Singer"], roles["Featured"]

        print("=" * 70)
        print("1) แยกศิลปินที่เป็นการฟีเจอริ่ง")
        print("=" * 70)
        for name in COLLABS:
            row = db.query_one("SELECT ArtistID FROM dbo.Artist WHERE ArtistName = ?", (name,))
            if not row:
                print(f"  - {name}: ไม่พบ (ข้าม)")
                continue
            collab_id = row["ArtistID"]
            parts = [p.strip() for p in re.split(r"\s*&\s*", name) if p.strip()]
            print(f"  {name} (#{collab_id}) -> {parts}")

            ids = []
            for part in parts:
                found = db.query_one("SELECT ArtistID FROM dbo.Artist WHERE ArtistName = ?", (part,))
                if found:
                    ids.append(found["ArtistID"])
                else:
                    print(f"      + สร้างศิลปินใหม่: {part}")
                    if apply:
                        db.execute("INSERT INTO dbo.Artist (ArtistName, Country) VALUES (?, N'TH')", (part,))
                        ids.append(db.query_one(
                            "SELECT ArtistID FROM dbo.Artist WHERE ArtistName = ?", (part,))["ArtistID"])
                    else:
                        ids.append(None)

            songs = db.query("SELECT DISTINCT SongID FROM dbo.Song_Artist_Role WHERE ArtistID = ?",
                             (collab_id,))
            if apply:
                for song in songs:
                    for index, artist_id in enumerate(ids):
                        if artist_id is None:
                            continue
                        role_id = singer if index == 0 else featured
                        exists = db.query_one(
                            "SELECT 1 AS x FROM dbo.Song_Artist_Role WHERE SongID = ? AND ArtistID = ? AND RoleID = ?",
                            (song["SongID"], artist_id, role_id))
                        if not exists:
                            db.execute(
                                "INSERT INTO dbo.Song_Artist_Role (SongID, ArtistID, RoleID) VALUES (?, ?, ?)",
                                (song["SongID"], artist_id, role_id))
                db.execute("DELETE FROM dbo.Song_Artist_Role WHERE ArtistID = ?", (collab_id,))
                db.execute("DELETE FROM dbo.Artist WHERE ArtistID = ?", (collab_id,))
            print(f"      เพลงที่ย้าย: {len(songs)}")

        print()
        print("=" * 70)
        print("2) รวมศิลปินที่ชื่อซ้ำ")
        print("=" * 70)
        for alias, canonical in ALIASES.items():
            a = db.query_one("SELECT ArtistID FROM dbo.Artist WHERE ArtistName = ?", (alias,))
            c = db.query_one("SELECT ArtistID FROM dbo.Artist WHERE ArtistName = ?", (canonical,))
            if not a or not c:
                print(f"  - {alias} -> {canonical}: ไม่พบ (ข้าม)")
                continue
            print(f"  {alias} (#{a['ArtistID']}) -> {canonical} (#{c['ArtistID']})")
            if apply:
                rows = db.query("SELECT SongID, RoleID FROM dbo.Song_Artist_Role WHERE ArtistID = ?",
                                (a["ArtistID"],))
                for r in rows:
                    exists = db.query_one(
                        "SELECT 1 AS x FROM dbo.Song_Artist_Role WHERE SongID = ? AND ArtistID = ? AND RoleID = ?",
                        (r["SongID"], c["ArtistID"], r["RoleID"]))
                    if not exists:
                        db.execute(
                            "INSERT INTO dbo.Song_Artist_Role (SongID, ArtistID, RoleID) VALUES (?, ?, ?)",
                            (r["SongID"], c["ArtistID"], r["RoleID"]))
                db.execute("DELETE FROM dbo.Song_Artist_Role WHERE ArtistID = ?", (a["ArtistID"],))
                db.execute("DELETE FROM dbo.Artist WHERE ArtistID = ?", (a["ArtistID"],))

        print()
        print("=" * 70)
        print("3) ลบเพลงซ้ำ (ชื่อ + ศิลปินหลัก เดียวกัน)")
        print("=" * 70)
        dupes = db.query("""
            SELECT s.SongID, s.SongTitle, s.PlayCount, sar.ArtistID
            FROM dbo.Song s
            JOIN dbo.Song_Artist_Role sar ON sar.SongID = s.SongID
            JOIN dbo.[Role] r ON r.RoleID = sar.RoleID
            WHERE r.[Role] = 'Singer'
            ORDER BY s.SongTitle, s.SongID
        """)
        groups: dict[tuple[str, int], list[dict]] = {}
        for row in dupes:
            groups.setdefault((row["SongTitle"], row["ArtistID"]), []).append(row)

        removed = 0
        for (title, artist_id), songs in groups.items():
            if len(songs) < 2:
                continue
            keep = songs[0]
            drops = songs[1:]
            print(f"  {title} — เก็บ #{keep['SongID']}, ลบ {[d['SongID'] for d in drops]}")
            if apply:
                for drop in drops:
                    db.execute("UPDATE dbo.History SET SongID = ? WHERE SongID = ?",
                               (keep["SongID"], drop["SongID"]))
                    db.execute("""DELETE FROM dbo.Playlist_Detail
                                   WHERE SongID = ?
                                     AND PlaylistID IN (SELECT PlaylistID FROM dbo.Playlist_Detail
                                                        WHERE SongID = ?)""",
                               (drop["SongID"], keep["SongID"]))
                    db.execute("UPDATE dbo.Playlist_Detail SET SongID = ? WHERE SongID = ?",
                               (keep["SongID"], drop["SongID"]))
                    db.execute("UPDATE dbo.Song SET PlayCount = PlayCount + ? WHERE SongID = ?",
                               (drop["PlayCount"], keep["SongID"]))
                    db.execute("DELETE FROM dbo.Song WHERE SongID = ?", (drop["SongID"],))
                    removed += 1

        print()
        print("โหมด:", "เขียนฐานข้อมูลจริง" if apply else "dry run (ยังไม่แก้อะไร)")
        print("ศิลปินคงเหลือ:", db.query_one("SELECT COUNT(*) AS n FROM dbo.Artist")["n"],
              "· เพลงคงเหลือ:", db.query_one("SELECT COUNT(*) AS n FROM dbo.Song")["n"],
              "· ลบเพลงซ้ำ:", removed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
