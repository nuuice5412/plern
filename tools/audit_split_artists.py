"""หาคู่ศิลปินอื่นที่อาจถูกแยกผิด (สองคนมีชุดเพลงเหมือนกันเป๊ะ)"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import create_app, db  # noqa: E402

app = create_app()
with app.app_context():
    rows = db.query("""
        SELECT a.ArtistID, a.ArtistName,
               (SELECT COUNT(*) FROM dbo.Song_Artist_Role sar WHERE sar.ArtistID = a.ArtistID) AS Roles,
               (SELECT COUNT(*) FROM dbo.Song_Artist_Role sar
                 WHERE sar.ArtistID = a.ArtistID AND sar.RoleID =
                       (SELECT RoleID FROM dbo.[Role] WHERE [Role] = 'Singer')) AS Sings
        FROM dbo.Artist a
        WHERE EXISTS (SELECT 1 FROM dbo.Song_Artist_Role sar WHERE sar.ArtistID = a.ArtistID
                      AND sar.RoleID = (SELECT RoleID FROM dbo.[Role] WHERE [Role] = 'Singer'))
    """)

    sets = {}
    for row in rows:
        songs = db.query(
            "SELECT SongID FROM dbo.Song_Artist_Role WHERE ArtistID = ? AND RoleID = "
            "(SELECT RoleID FROM dbo.[Role] WHERE [Role] = 'Singer')", (row["ArtistID"],))
        key = frozenset(s["SongID"] for s in songs)
        sets.setdefault(key, []).append(row["ArtistName"])

    print("คู่ที่ร้องเพลงชุดเดียวกันเป๊ะ (อาจเป็นวงเดียวกันถูกแยก):")
    found = 0
    for key, names in sets.items():
        if len(names) > 1 and len(key) >= 2:
            print("  -", names, f"({len(key)} เพลง)")
            found += 1
    if not found:
        print("  ไม่พบ")
