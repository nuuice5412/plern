"""
fix_artist_photos.py - re-resolve Deezer artist photos by track, not just by name

Why: `fetch_artwork.py` matches "the artist with the most fans whose name is similar",
so a same-name band can win (e.g. the German *Paradox* instead of the Thai one).

This script resolves the artist from a song we already have:
    1. search the track title on Deezer  ->  the track tells us who really sings it
    2. if the singer's name matches, take that artist's picture
    3. otherwise fall back to the artist search + top-track overlap
    4. if the confidence is still low, leave the current photo alone and list it

Usage
    python tools/fix_artist_photos.py --dry-run     # report only
    python tools/fix_artist_photos.py               # replace when confident
    python tools/fix_artist_photos.py --min 0.85
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from fetch_artwork import load_artists, similarity  # noqa: E402

IMG_DIR = ROOT / "app" / "static" / "img"
MANIFEST = IMG_DIR / "manifest.json"
HEADERS = {"User-Agent": "PlernCourseProject/1.0"}
PAUSE = 0.3


def api(session: requests.Session, path: str) -> dict:
    for _ in range(3):
        try:
            data = session.get("https://api.deezer.com" + path, timeout=15).json()
            if isinstance(data, dict) and data.get("error"):
                time.sleep(1.5)
                continue
            return data
        except requests.RequestException:
            time.sleep(1.5)
    return {}


def song_titles(artist_id: int) -> list[str]:
    import pyodbc

    from app.config import Config

    with pyodbc.connect(Config.CONNECTION_STRING, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 5 s.SongTitle FROM dbo.Song_Artist_Role sar "
            "JOIN dbo.Song s ON s.SongID = sar.SongID "
            "WHERE sar.ArtistID = ? ORDER BY s.PlayCount DESC",
            artist_id,
        )
        return [row[0] for row in cursor.fetchall()]


def resolve_by_track(session: requests.Session, name: str, titles: list[str]):
    """The strongest signal: find one of our songs and see who Deezer credits it to."""
    for title in titles:
        clean = title.split("(")[0].strip()
        data = api(session, f"/search/track?q={requests.utils.quote(clean)}&limit=10")
        time.sleep(PAUSE)
        for track in data.get("data", []):
            singer = track.get("artist", {})
            singer_name = singer.get("name", "")
            if similarity(name, singer_name) >= 0.80 and similarity(title, track.get("title", "")) >= 0.60:
                return singer, f"เจอจากเพลง “{clean}”"
    return None, ""


def resolve_by_name(session: requests.Session, name: str, titles: list[str]):
    data = api(session, f"/search/artist?q={requests.utils.quote(name)}&limit=10")
    candidates = [c for c in data.get("data", [])
                  if c.get("picture_big") and "/artist//" not in c["picture_big"]]
    best, best_score = None, 0.0
    for candidate in candidates[:4]:
        name_score = similarity(name, candidate.get("name", ""))
        if name_score < 0.55:
            continue
        top = api(session, f"/artist/{candidate['id']}/top?limit=10")
        time.sleep(PAUSE)
        track_score = max(
            (similarity(t.get("title", ""), ours)
             for t in top.get("data", []) for ours in titles),
            default=0.0,
        )
        score = 0.65 * name_score + 0.35 * track_score
        if score > best_score:
            best, best_score = candidate, score
    return best, best_score


def download(session: requests.Session, url: str, target: pathlib.Path) -> bool:
    try:
        response = session.get(url, timeout=20, stream=True)
    except requests.RequestException:
        return False
    if response.status_code != 200 or "image" not in response.headers.get("Content-Type", ""):
        return False
    with open(target, "wb") as handle:
        for chunk in response.iter_content(64 * 1024):
            handle.write(chunk)
    return target.stat().st_size > 2_000


def main() -> int:
    parser = argparse.ArgumentParser(description="แก้รูปศิลปินที่จับคู่ผิด โดยค้นจากชื่อเพลง")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min", type=float, default=0.80, help="คะแนนขั้นต่ำ (0.80)")
    parser.add_argument("--only", default="")
    args = parser.parse_args()

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"covers": {}, "artists": {}}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    manifest.setdefault("covers", {})
    manifest.setdefault("artists", {})

    session = requests.Session()
    session.headers.update(HEADERS)

    artists = load_artists()
    if args.only:
        artists = [a for a in artists if args.only.lower() in a["ArtistName"].lower()]

    fixed, kept, missing = [], [], []
    for artist in artists:
        artist_id, name = artist["ArtistID"], artist["ArtistName"]
        titles = song_titles(artist_id)
        target = IMG_DIR / f"artist_{artist_id}.jpg"

        singer, how = resolve_by_track(session, name, titles)
        confidence, candidate = 0.0, singer
        if singer is None:
            candidate, confidence = resolve_by_name(session, name, titles)
            how = "ค้นด้วยชื่อศิลปิน"
            if candidate:
                confidence = confidence
        else:
            confidence = 1.0

        if candidate is None:
            missing.append(name)
            print(f"  {name:<24} ✗ หาไม่เจอ")
            continue
        if confidence < args.min:
            kept.append(f"{name} ({confidence:.2f})")
            print(f"  {name:<24} ~ ไม่มั่นใจ {confidence:.2f} — คงรูปเดิม")
            continue

        image_url = (candidate.get("picture_big") or candidate.get("picture_medium") or "")
        if not image_url:
            missing.append(name)
            print(f"  {name:<24} ✗ ไม่มีรูป")
            continue

        print(f"  {name:<24} ✓ {candidate.get('name')} [{how}]")
        if args.dry_run:
            fixed.append(name)
            continue

        if download(session, image_url, target):
            manifest["artists"][str(artist_id)] = target.name
            MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            fixed.append(name)
        else:
            missing.append(name)

    print(f"\nอัปเดต {len(fixed)} · ไม่มั่นใจ {len(kept)} · ไม่เจอ {len(missing)}")
    if kept:
        print("ควรตรวจด้วยตา: " + ", ".join(kept))
    if missing:
        print("ไม่มีรูป: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
