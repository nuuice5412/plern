"""
fetch_credits.py - real songwriting credits from public music databases

`sync_catalog.py` invents Composer/Producer for every song (it just reuses the
performer). This script replaces those guesses with **real** data where a public
database actually knows the song, and records where each credit came from.

Sources, tried in order:
    1. MusicBrainz   (free, no key) - recording -> work -> "writer" relations
    2. MusicBrainz   release-level "producer" relations (when present)

Anything not found is reported, never invented.

Usage
    python tools/fetch_credits.py --dry-run          # report coverage only
    python tools/fetch_credits.py                    # write real credits
    python tools/fetch_credits.py --prune            # also delete invented rows
    python tools/fetch_credits.py --limit 30
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.parse

import pyodbc
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from app.config import Config  # noqa: E402
from fetch_artwork import similarity  # noqa: E402

UA = {"User-Agent": "PlernCourseProject/1.0 ( educational demo )"}
BASE = "https://musicbrainz.org/ws/2"
REPORT = ROOT / "data" / "credits_report.json"
PAUSE = 1.1          # MusicBrainz allows ~1 request/second


def get(path: str, params: dict) -> dict:
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(dict(params, fmt="json"))
    for _ in range(3):
        try:
            response = requests.get(url, headers=UA, timeout=20)
        except requests.RequestException:
            time.sleep(2)
            continue
        if response.status_code == 200:
            return response.json()
        if response.status_code in (503, 429):
            time.sleep(2.5)
            continue
        return {}
    return {}


def find_recording(title: str, artist: str) -> dict | None:
    data = get("recording", {"query": f'recording:"{title}" AND artist:"{artist}"', "limit": 3})
    for candidate in data.get("recordings", []):
        if int(candidate.get("score", 0)) < 90:
            continue
        credits = candidate.get("artist-credit") or []
        name = "".join(part.get("name", "") for part in credits)
        if similarity(title, candidate.get("title", "")) >= 0.80 and similarity(artist, name) >= 0.60:
            return candidate
    return None


def writers_for(recording_id: str) -> list[str]:
    detail = get(f"recording/{recording_id}", {"inc": "work-rels"})
    time.sleep(PAUSE)
    names: list[str] = []
    for relation in detail.get("relations", []):
        if relation.get("target-type") != "work":
            continue
        work = get(f"work/{relation['work']['id']}", {"inc": "artist-rels"})
        time.sleep(PAUSE)
        for rel in work.get("relations", []):
            if rel.get("type") in ("writer", "composer", "lyricist"):
                name = rel.get("artist", {}).get("name")
                if name and name not in names:
                    names.append(name)
    return names


def role_ids(cursor) -> dict[str, int]:
    cursor.execute("SELECT RoleID, [Role] FROM dbo.[Role]")
    return {name: rid for rid, name in cursor.fetchall()}


def artist_id(cursor, name: str) -> int:
    cursor.execute("SELECT ArtistID FROM dbo.Artist WHERE ArtistName = ?", name)
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute(
        "INSERT INTO dbo.Artist (ArtistName, Country, Bio) OUTPUT INSERTED.ArtistID VALUES (?, NULL, NULL)",
        name,
    )
    return cursor.fetchone()[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="ดึงเครดิตแต่งเพลงจริงจาก MusicBrainz")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prune", action="store_true",
                        help="ลบ Composer/Producer ที่สร้างขึ้นและไม่มีข้อมูลจริงรองรับ")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    with pyodbc.connect(Config.CONNECTION_STRING, autocommit=True) as conn:
        cursor = conn.cursor()
        roles = role_ids(cursor)
        composer_id = roles.get("Composer")
        producer_id = roles.get("Producer")
        if not composer_id:
            raise SystemExit("ไม่พบ Role 'Composer' ในฐานข้อมูล")

        cursor.execute("""
            SELECT s.SongID, s.SongTitle, vd.MainArtistName
            FROM dbo.Song s JOIN dbo.vw_SongDetail vd ON vd.SongID = s.SongID
            ORDER BY s.SongID
        """)
        songs = cursor.fetchall()
        if args.limit:
            songs = songs[: args.limit]

        report: dict[str, dict] = {}
        found = missing = 0
        print(f"ตรวจ {len(songs)} เพลง (MusicBrainz)\n")

        for song_id, title, artist in songs:
            recording = find_recording(title, artist)
            time.sleep(PAUSE)
            if recording is None:
                missing += 1
                report[str(song_id)] = {"title": title, "artist": artist, "source": None}
                continue

            writers = writers_for(recording["id"])
            if not writers:
                missing += 1
                report[str(song_id)] = {"title": title, "artist": artist,
                                        "source": "musicbrainz", "writers": []}
                continue

            found += 1
            report[str(song_id)] = {"title": title, "artist": artist,
                                    "source": "musicbrainz", "writers": writers}
            print(f"  {title[:36]:<38} -> {', '.join(writers[:3])}")

            if args.dry_run:
                continue

            # replace the invented composer credits with the real writers
            cursor.execute(
                "DELETE FROM dbo.Song_Artist_Role WHERE SongID = ? AND RoleID = ?",
                (song_id, composer_id),
            )
            for name in writers:
                aid = artist_id(cursor, name)
                cursor.execute(
                    "INSERT INTO dbo.Song_Artist_Role (SongID, ArtistID, RoleID) "
                    "SELECT ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM dbo.Song_Artist_Role "
                    "WHERE SongID = ? AND ArtistID = ? AND RoleID = ?)",
                    (song_id, aid, composer_id, song_id, aid, composer_id),
                )

        print(f"\nเจอข้อมูลจริง {found} เพลง · ไม่พบ {missing} เพลง")

        if args.prune and not args.dry_run:
            # songs with no real credit lose the invented composer/producer rows
            removed = 0
            for song_id, info in report.items():
                if info.get("writers"):
                    continue
                for role_id in (composer_id, producer_id):
                    if not role_id:
                        continue
                    cursor.execute(
                        "DELETE FROM dbo.Song_Artist_Role WHERE SongID = ? AND RoleID = ?",
                        (int(song_id), role_id),
                    )
                    removed += cursor.rowcount
            print(f"ลบเครดิตที่สร้างขึ้น {removed} แถว (ไม่มีข้อมูลจริงรองรับ)")

    if not args.dry_run:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"บันทึกหลักฐานที่มา: {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
