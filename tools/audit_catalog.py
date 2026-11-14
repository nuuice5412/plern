"""ตรวจคุณภาพข้อมูลหลังเพิ่มคลังเป็น 787 เพลง"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import create_app, db  # noqa: E402

app = create_app()
with app.app_context():
    total = db.query_one("SELECT COUNT(*) AS n FROM dbo.Song")["n"]
    print(f"เพลงทั้งหมด: {total}")

    dupes = db.query("""
        SELECT s.SongTitle, a.ArtistName, COUNT(*) AS n
        FROM dbo.Song s
        JOIN dbo.Song_Artist_Role sar ON sar.SongID = s.SongID
        JOIN dbo.Artist a ON a.ArtistID = sar.ArtistID
        JOIN dbo.[Role] r ON r.RoleID = sar.RoleID
        WHERE r.[Role] = 'Singer'
        GROUP BY s.SongTitle, a.ArtistName
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC, s.SongTitle
    """)
    print(f"\nชื่อเพลงซ้ำ (ศิลปินเดียวกัน): {len(dupes)} กลุ่ม")
    for d in dupes[:8]:
        print(f"  {d['n']}x {d['SongTitle']} — {d['ArtistName']}")

    no_singer = db.query("""
        SELECT COUNT(*) AS n FROM dbo.Song s
        WHERE NOT EXISTS (
            SELECT 1 FROM dbo.Song_Artist_Role sar
            JOIN dbo.[Role] r ON r.RoleID = sar.RoleID
            WHERE sar.SongID = s.SongID AND r.[Role] = 'Singer')
    """)[0]["n"]
    print(f"\nเพลงที่ไม่มีนักร้องหลัก: {no_singer}")

    no_audio_rows = db.query("SELECT SongID FROM dbo.Song")
    manifest = json.loads(
        (pathlib.Path(__file__).resolve().parent.parent /
         "app" / "static" / "audio" / "manifest.json").read_text(encoding="utf-8"))
    tracks = manifest.get("tracks", manifest)
    missing_audio = [r["SongID"] for r in no_audio_rows if str(r["SongID"]) not in tracks]
    print(f"เพลงที่ไม่มีไฟล์เสียง: {len(missing_audio)} -> {missing_audio}")

    imgs = json.loads(
        (pathlib.Path(__file__).resolve().parent.parent /
         "app" / "static" / "img" / "manifest.json").read_text(encoding="utf-8"))
    covers = imgs.get("covers", {})
    artists = imgs.get("artists", {})
    print(f"\nรูปปก: {len(covers)} · รูปศิลปิน: {len(artists)}")

    performers = db.query("""
        SELECT COUNT(DISTINCT a.ArtistID) AS n FROM dbo.Artist a
        JOIN dbo.Song_Artist_Role sar ON sar.ArtistID = a.ArtistID
        JOIN dbo.[Role] r ON r.RoleID = sar.RoleID
        WHERE r.[Role] IN ('Singer', 'Featured')
    """)[0]["n"]
    without_photo = db.query("""
        SELECT a.ArtistID, a.ArtistName FROM dbo.Artist a
        WHERE EXISTS (SELECT 1 FROM dbo.Song_Artist_Role sar
                      JOIN dbo.[Role] r ON r.RoleID = sar.RoleID
                      WHERE sar.ArtistID = a.ArtistID AND r.[Role] IN ('Singer','Featured'))
    """)
    missing_photo = [a for a in without_photo if str(a["ArtistID"]) not in artists]
    print(f"ศิลปินที่แสดงบนหน้าเว็บ: {performers} · ยังไม่มีรูป: {len(missing_photo)}")
    for a in missing_photo[:10]:
        print("   -", a["ArtistName"])

    plays = db.query_one("SELECT MIN(PlayCount) AS lo, MAX(PlayCount) AS hi, "
                         "SUM(CASE WHEN PlayCount = 0 THEN 1 ELSE 0 END) AS zero FROM dbo.Song")
    print(f"\nยอดฟัง: ต่ำสุด {plays['lo']} · สูงสุด {plays['hi']} · เพลงที่ยังไม่มีคนฟัง {plays['zero']}")
