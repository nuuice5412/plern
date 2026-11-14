"""
fetch_artist_spotify.py - artist photos from the Spotify Web API

Spotify has the cleanest artist images (official, 320-640 px) but needs credentials:
create a free app at https://developer.spotify.com/dashboard and set

    set SPOTIFY_CLIENT_ID=...
    set SPOTIFY_CLIENT_SECRET=...

The script uses the Client Credentials flow (no browser login) and writes
app/static/img/artist_<ArtistID>.jpg + updates app/static/img/manifest.json.

Matching is stricter than the Deezer version: it scores the name AND checks the
candidate's top tracks against the songs we actually have in the database, so a
same-name artist with different songs is rejected.

Usage
    python tools/fetch_artist_spotify.py --dry-run      # preview matches only
    python tools/fetch_artist_spotify.py                # fetch missing artists
    python tools/fetch_artist_spotify.py --force        # re-download everything
    python tools/fetch_artist_spotify.py --only "Palmy"
    python tools/fetch_artist_spotify.py --min-score 0.7
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import sys
import time
import urllib.parse

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from fetch_artwork import load_artists, similarity  # noqa: E402

TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
IMG_DIR = ROOT / "app" / "static" / "img"
MANIFEST = IMG_DIR / "manifest.json"
TIMEOUT = 20
PAUSE = 0.34          # stay well under Spotify's rate limit


def get_token(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    headers = {"Authorization": "Basic " + base64.b64encode(raw).decode()}
    response = requests.post(TOKEN_URL, data={"grant_type": "client_credentials"},
                             headers=headers, timeout=TIMEOUT)
    if response.status_code != 200:
        raise SystemExit(
            f"ขอ token ไม่สำเร็จ ({response.status_code}): {response.text[:200]}\n"
            "ตรวจ SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET อีกครั้ง"
        )
    return response.json()["access_token"]


def spotify_get(session: requests.Session, path: str, **params) -> dict:
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    response = session.get(url, timeout=TIMEOUT)
    if response.status_code == 429:
        wait = int(response.headers.get("Retry-After", "2"))
        time.sleep(wait)
        response = session.get(url, timeout=TIMEOUT)
    if response.status_code != 200:
        return {}
    return response.json()


def best_track_score(session: requests.Session, artist_id: str, our_titles: list[str]) -> float:
    """How well does this Spotify artist's catalogue overlap with our songs?"""
    data = spotify_get(session, f"/artists/{artist_id}/top-tracks", market="TH")
    tracks = data.get("tracks", [])
    if not tracks:
        return 0.0
    best = 0.0
    for track in tracks[:10]:
        title = track.get("name", "")
        for ours in our_titles:
            best = max(best, similarity(title, ours))
    return best


def pick_candidate(session: requests.Session, name: str, our_titles: list[str]) -> tuple[dict | None, float, str]:
    data = spotify_get(session, "/search", q=name, type="artist", limit=10, market="TH")
    candidates = data.get("artists", {}).get("items", [])
    if not candidates:
        return None, 0.0, "ไม่พบใน Spotify"

    scored = []
    for candidate in candidates[:5]:
        name_score = similarity(name, candidate.get("name", ""))
        if name_score < 0.55:
            continue
        time.sleep(PAUSE)
        track_score = best_track_score(session, candidate["id"], our_titles)
        score = 0.65 * name_score + 0.35 * track_score
        scored.append((score, name_score, track_score, candidate))

    if not scored:
        return None, 0.0, "ชื่อไม่ใกล้เคียงเลย"

    scored.sort(key=lambda row: row[0], reverse=True)
    score, name_score, track_score, best = scored[0]
    detail = f"ชื่อ {name_score:.2f} · เพลงตรง {track_score:.2f}"
    return best, score, detail


def download_image(session: requests.Session, url: str, target: pathlib.Path) -> bool:
    response = session.get(url, timeout=TIMEOUT, stream=True)
    if response.status_code != 200:
        return False
    content_type = response.headers.get("Content-Type", "")
    if "image" not in content_type:
        return False
    with open(target, "wb") as handle:
        for chunk in response.iter_content(64 * 1024):
            handle.write(chunk)
    return target.stat().st_size > 2_000


def main() -> int:
    parser = argparse.ArgumentParser(description="ดึงรูปศิลปินจาก Spotify Web API")
    parser.add_argument("--dry-run", action="store_true", help="ดูผลจับคู่ก่อน ไม่ดาวน์โหลด")
    parser.add_argument("--force", action="store_true", help="ดาวน์โหลดใหม่ทับของเดิม")
    parser.add_argument("--only", default="", help="ทำเฉพาะศิลปินที่ชื่อมีคำนี้")
    parser.add_argument("--min-score", type=float, default=0.72,
                        help="คะแนนขั้นต่ำที่จะยอมรับ (ค่าเริ่มต้น 0.72)")
    args = parser.parse_args()

    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print("ยังไม่ได้ตั้งค่า SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET\n")
        print("1) เปิด https://developer.spotify.com/dashboard แล้วกด Create app")
        print("2) คัดลอก Client ID และ Client secret")
        print("3) รันใน PowerShell:")
        print('   $env:SPOTIFY_CLIENT_ID="..."')
        print('   $env:SPOTIFY_CLIENT_SECRET="..."')
        return 2

    token = get_token(client_id, client_secret)
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"covers": {}, "artists": {}}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    manifest.setdefault("covers", {})
    manifest.setdefault("artists", {})

    artists = load_artists()
    if args.only:
        needle = args.only.lower()
        artists = [a for a in artists if needle in a["ArtistName"].lower()]

    print(f"ศิลปินทั้งหมด {len(artists)} คน · ขั้นต่ำ {args.min_score:.2f}"
          f"{' · โหมดทดลอง' if args.dry_run else ''}\n")

    # our song titles per artist — the signal that distinguishes same-name artists
    from app.config import Config
    import pyodbc

    with pyodbc.connect(Config.CONNECTION_STRING, timeout=10) as conn:
        cursor = conn.cursor()
        titles: dict[int, list[str]] = {}
        cursor.execute(
            "SELECT sar.ArtistID, s.SongTitle FROM dbo.Song_Artist_Role sar "
            "JOIN dbo.Song s ON s.SongID = sar.SongID"
        )
        for artist_id, title in cursor.fetchall():
            titles.setdefault(artist_id, []).append(title)

    updated = skipped = failed = 0
    for artist in artists:
        artist_id = artist["ArtistID"]
        name = artist["ArtistName"]
        target = IMG_DIR / f"artist_{artist_id}.jpg"

        if target.exists() and not args.force:
            print(f"  {name:<28} มีรูปแล้ว (ข้าม)")
            skipped += 1
            continue

        candidate, score, detail = pick_candidate(session, name, titles.get(artist_id, []))
        time.sleep(PAUSE)

        if candidate is None:
            print(f"  {name:<28} ✗ {detail}")
            failed += 1
            continue

        images = candidate.get("images") or []
        if not images:
            print(f"  {name:<28} ✗ ไม่มีรูป ({detail})")
            failed += 1
            continue

        if score < args.min_score:
            print(f"  {name:<28} ✗ คะแนนต่ำ {score:.2f} ({detail}) -> {candidate.get('name')}")
            failed += 1
            continue

        best_image = max(images, key=lambda img: img.get("width") or 0)
        label = f"  {name:<28} ✓ {candidate['name']} [{score:.2f}] {detail}"
        if args.dry_run:
            print(label + f" -> {best_image.get('width')}px")
            updated += 1
            continue

        if download_image(session, best_image["url"], target):
            manifest["artists"][str(artist_id)] = target.name
            MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            print(label + f" -> {best_image.get('width')}px")
            updated += 1
        else:
            print(f"  {name:<28} ✗ ดาวน์โหลดไม่สำเร็จ")
            failed += 1

    print(f"\nอัปเดต {updated} · ข้าม {skipped} · ไม่ผ่าน {failed}")
    if not args.dry_run and updated:
        print("รีเฟรชหน้าเว็บเพื่อดูรูปใหม่ (manifest ถูกอ่านใหม่เมื่อไฟล์เปลี่ยน)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
