"""
เพิ่มเพลงจากลิงก์ Spotify playlist ที่ผู้ใช้ให้ (เฉพาะที่ยังไม่มีในฐานข้อมูล)

ขั้นตอน
  1) อ่าน data/spotify_playlist.json (ชื่อเพลง + ศิลปิน จากหน้า embed)
  2) เช็คในฐานข้อมูลก่อน (ชื่อเพลง + ศิลปิน ตรงกัน) -> ข้ามถ้ามีแล้ว
  3) ค้น iTunes เพื่อเอา metadata จริง (ชื่อ, ความยาว, วันวางจำหน่าย, ปก)
  4) insert ด้วยรูปแบบเดียวกับ tools/sync_catalog.py

ใช้:  python tools/add_from_playlist.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sync_catalog import (  # noqa: E402
    ITUNES_SEARCH, ensure_artist, get_conn, insert_song_row, link_roles,
    seed_plays, song_exists, title_key, split_artists, feat_from_title, norm,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAYLIST = ROOT / "data" / "spotify_playlist.json"
COUNTRY = "TH"
PAUSE = 0.4


def search_track(session: requests.Session, title: str, artist: str) -> dict | None:
    """หาผลลัพธ์ iTunes ที่ตรงที่สุดสำหรับ (ชื่อเพลง, ศิลปิน)"""
    query = f"{title} {split_artists(artist)[0] if artist else ''}".strip()
    try:
        res = session.get(ITUNES_SEARCH, params={
            "term": query, "country": COUNTRY, "media": "music",
            "entity": "song", "limit": 10,
        }, timeout=20)
        res.raise_for_status()
        results = res.json().get("results", [])
    except requests.RequestException:
        return None

    def pick(results, strict):
        wanted_title = title_key(title)
        best, best_score = None, 0.0
        for item in results:
            if item.get("kind") != "song" or not item.get("previewUrl"):
                continue
            got = title_key(item.get("trackName", ""))
            score = 1.0 if got == wanted_title else 0.0
            if not score and (wanted_title[0] in got[0] or got[0] in wanted_title[0]):
                score = 0.6
            if score > best_score:
                best, best_score = item, score
        threshold = 0.6 if strict else 0.6
        return best if best_score >= threshold else None

    chosen = pick(results, True)
    if chosen:
        return chosen

    # ลองอีกครั้งด้วยชื่อเพลงอย่างเดียว (ศิลปินอาจสะกดต่างจากใน Spotify)
    if artist:
        try:
            res = session.get(ITUNES_SEARCH, params={
                "term": title, "country": COUNTRY, "media": "music",
                "entity": "song", "limit": 15,
            }, timeout=20)
            again = res.json().get("results", [])
        except Exception:
            again = []
        return pick(again, False)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--plays", type=int, default=3)
    args = ap.parse_args()

    data = json.loads(PLAYLIST.read_text(encoding="utf-8"))
    tracks = data["tracks"]
    print(f"เพลย์ลิสต์: {data.get('name')} · {len(tracks)} เพลง")

    session = requests.Session()
    session.headers.update({"User-Agent": "plern/1.0"})

    added = skipped = missing = 0
    conn = get_conn()
    cursor = conn.cursor()

    for index, track in enumerate(tracks, 1):
        title = (track.get("title") or "").strip()
        artist = (track.get("artist") or "").strip()
        if not title:
            continue

        primary = split_artists(artist)[0] if artist else ""
        if primary:
            cursor.execute(
                "SELECT ArtistID FROM dbo.Artist WHERE ArtistName = ?", primary)
            row = cursor.fetchone()
            if row and song_exists(cursor, title, row[0]):
                skipped += 1
                print(f"[{index:>3}/{len(tracks)}] = มีแล้ว  {title} — {artist}")
                continue

        item = search_track(session, title, artist)
        if not item:
            missing += 1
            print(f"[{index:>3}/{len(tracks)}] x ไม่พบใน iTunes  {title} — {artist}")
            time.sleep(PAUSE)
            continue

        if args.dry_run:
            added += 1
            print(f"[{index:>3}/{len(tracks)}] + {item['trackName']} — {item['artistName']}")
            time.sleep(PAUSE)
            continue

        primary_id = ensure_artist(cursor, item["artistName"], COUNTRY)
        if song_exists(cursor, item["trackName"], primary_id):
            skipped += 1
            print(f"[{index:>3}/{len(tracks)}] = มีแล้ว  {item['trackName']}")
            time.sleep(PAUSE)
            continue

        song_id = insert_song_row(cursor, item)
        featured = [ensure_artist(cursor, name, COUNTRY)
                    for name in feat_from_title(item["trackName"])]
        link_roles(cursor, song_id, primary_id, featured)
        if args.plays:
            seed_plays(cursor, song_id, args.plays)
        conn.commit()
        added += 1
        print(f"[{index:>3}/{len(tracks)}] + #{song_id} {item['trackName']} — {item['artistName']}")
        time.sleep(PAUSE)

    cursor.close()
    conn.close()
    print(f"\nเพิ่ม {added} · มีอยู่แล้ว {skipped} · หาไม่เจอ {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
