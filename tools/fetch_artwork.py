"""
fetch_artwork.py - fetch "song covers" and "artist photos" to use in the UI

Sources
  Covers     : iTunes Lookup API (lookup?id=<trackId>) gives the real album artwork
             uses the trackId that tools/fetch_previews.py saved in
             app/static/audio/manifest.json -> no guessing or mismatched names
  Artist pic : Deezer Search Artist API (picture_big 500x500) — no key required
             picks the closest-matching name, then the one with the most fans
             (guards against same-named artists that are a different band)

Doesn't touch the database schema: stores files + manifest.json like the audio files
    app/static/img/cover_<SongID>.jpg
    app/static/img/artist_<ArtistID>.jpg
    app/static/img/manifest.json

Usage
    python tools/fetch_artwork.py                # fetch what's missing
    python tools/fetch_artwork.py --force        # re-fetch and overwrite
    python tools/fetch_artwork.py --dry-run      # preview matches, download nothing
    python tools/fetch_artwork.py --only-artists # artist photos only
    python tools/fetch_artwork.py --cover-size 600
"""

from __future__ import annotations

import argparse
import difflib
import json
import pathlib
import re
import sys
import time
import unicodedata

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IMG_DIR = ROOT / "app" / "static" / "img"
MANIFEST = IMG_DIR / "manifest.json"
AUDIO_MANIFEST = ROOT / "app" / "static" / "audio" / "manifest.json"

ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
DEEZER_ARTIST = "https://api.deezer.com/search/artist"
USER_AGENT = "SpiMusicCourseProject/1.0 (educational demo)"
PAUSE = 1.2
TIMEOUT = 25


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[\(\)\[\]\{\}.,!?'\"·•\-–—/\\|&+]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


# ---------------------------------------------------------------------------
# database
# ---------------------------------------------------------------------------
def load_artists() -> list[dict]:
    import pyodbc

    from app.config import Config

    with pyodbc.connect(Config.CONNECTION_STRING, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT a.ArtistID, a.ArtistName, "
            "(SELECT COUNT(*) FROM dbo.Song_Artist_Role sar WHERE sar.ArtistID = a.ArtistID) AS n "
            "FROM dbo.Artist a ORDER BY a.ArtistID"
        )
        return [
            {"ArtistID": r[0], "ArtistName": r[1], "Songs": r[2]} for r in cursor.fetchall()
        ]


# ---------------------------------------------------------------------------
# download image files
# ---------------------------------------------------------------------------
def download(session: requests.Session, url: str, target: pathlib.Path) -> bool:
    response = session.get(url, timeout=TIMEOUT, stream=True)
    if response.status_code != 200:
        return False
    content_type = response.headers.get("Content-Type", "")
    if "image" not in content_type:
        return False

    tmp = target.with_suffix(target.suffix + ".part")
    with tmp.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=32 * 1024):
            handle.write(chunk)
    if tmp.stat().st_size < 1024:            # too small to be a real image
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(target)
    return True


# ---------------------------------------------------------------------------
# covers: iTunes lookup by trackId
# ---------------------------------------------------------------------------
def fetch_covers(session: requests.Session, cover_size: int, force: bool,
                 dry_run: bool, manifest: dict) -> tuple[int, int, int]:
    if not AUDIO_MANIFEST.exists():
        print("[warn] ไม่พบ audio/manifest.json — ข้ามการดึงปก")
        return 0, 0, 0

    audio = json.loads(AUDIO_MANIFEST.read_text(encoding="utf-8"))
    tracks = audio.get("tracks", {})

    # song_id -> itunesTrackId
    pairs = {
        int(song_id): int(entry["itunesTrackId"])
        for song_id, entry in tracks.items()
        if entry.get("itunesTrackId")
    }
    print(f"เพลงที่มี trackId ให้ดึงปก: {len(pairs)} เพลง")

    todo = {sid: tid for sid, tid in pairs.items()
            if force or not (IMG_DIR / f"cover_{sid}.jpg").exists()}
    if not todo:
        print("  ปกครบแล้ว")
        return 0, len(pairs), 0

    if dry_run:
        for sid, tid in list(todo.items())[:10]:
            print(f"  #{sid:<4} trackId={tid}")
        print(f"  ... รวม {len(todo)} เพลง (dry-run ไม่โหลด)")
        return 0, len(pairs) - len(todo), 0

    # lookup in batches (iTunes accepts several ids separated by commas)
    cover_urls: dict[int, str] = {}
    id_to_song = {str(tid): sid for sid, tid in todo.items()}
    ids = list(id_to_song)
    for start in range(0, len(ids), 50):
        chunk = ids[start:start + 50]
        for country in ("TH", "US"):
            try:
                response = session.get(
                    ITUNES_LOOKUP,
                    params={"id": ",".join(chunk), "country": country},
                    timeout=TIMEOUT,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                print(f"  [warn] lookup ล้มเหลว ({country}): {exc}")
                continue

            for item in response.json().get("results", []):
                sid = id_to_song.get(str(item.get("trackId")))
                url = item.get("artworkUrl100")
                if sid and url and sid not in cover_urls:
                    cover_urls[sid] = url.replace("100x100bb", f"{cover_size}x{cover_size}bb")

            if len(cover_urls) >= len(todo):
                break
            time.sleep(PAUSE)

        time.sleep(PAUSE)

    downloaded = failed = 0
    for sid in sorted(todo):
        url = cover_urls.get(sid)
        if not url:
            print(f"  #{sid:<4} ไม่พบ artwork")
            failed += 1
            continue
        target = IMG_DIR / f"cover_{sid}.jpg"
        if download(session, url, target):
            manifest.setdefault("covers", {})[str(sid)] = target.name
            downloaded += 1
        else:
            print(f"  #{sid:<4} ดาวน์โหลดไม่สำเร็จ")
            failed += 1

    print(f"  ดาวน์โหลดปก {downloaded} | พลาด {failed}")
    return downloaded, 0, failed


# ---------------------------------------------------------------------------
# artist photos: Deezer
# ---------------------------------------------------------------------------
def pick_deezer_artist(name: str, candidates: list[dict]) -> tuple[dict | None, float]:
    """
    Pick an artist from the search results:
      1) Must have a real picture, and the name must be similar >= 0.90
      2) Name similarity is the main criterion (closest name wins) — not most fans,
         because a similarly named but different band often has more fans, e.g.
         "Only Monday" (94 fans) vs "Okay Monday" (734 fans)
      3) Fan count only breaks the tie when the names are too close to tell apart
    """
    scored = []
    for candidate in candidates:
        picture = candidate.get("picture_big") or ""
        if not picture or "/artist//" in picture:
            continue
        score = similarity(name, candidate.get("name", ""))
        if score >= 0.90:
            scored.append((score, candidate))

    if not scored:
        return None, 0.0

    best_score = max(score for score, _ in scored)
    near_best = [c for score, c in scored if score >= best_score - 0.03]
    best = max(near_best, key=lambda c: c.get("nb_fan", 0))
    return best, best_score


def fetch_artist_photos(session: requests.Session, force: bool, dry_run: bool,
                        manifest: dict) -> tuple[int, int, int]:
    artists = load_artists()
    print(f"ศิลปินในฐานข้อมูล: {len(artists)} คน")

    downloaded = skipped = failed = 0
    for artist in artists:
        artist_id = artist["ArtistID"]
        name = artist["ArtistName"]
        target = IMG_DIR / f"artist_{artist_id}.jpg"

        if target.exists() and not force:
            manifest.setdefault("artists", {})[str(artist_id)] = target.name
            skipped += 1
            continue

        try:
            response = session.get(DEEZER_ARTIST, params={"q": name, "limit": 5},
                                   timeout=TIMEOUT)
            response.raise_for_status()
            candidates = response.json().get("data", [])
        except requests.RequestException as exc:
            print(f"  {name:<24} ✗ เน็ตเวิร์ก: {exc}")
            failed += 1
            time.sleep(PAUSE)
            continue

        best, score = pick_deezer_artist(name, candidates)
        if best is None:
            print(f"  {name:<24} ✗ ไม่พบรูปที่ตรง")
            failed += 1
            time.sleep(PAUSE)
            continue

        if dry_run:
            print(f"  {name:<24} ✓ {best['name']} (fans {best.get('nb_fan', 0)}, "
                  f"คะแนน {score:.2f})")
            time.sleep(PAUSE)
            continue

        if download(session, best["picture_big"], target):
            manifest.setdefault("artists", {})[str(artist_id)] = target.name
            downloaded += 1
            print(f"  {name:<24} ✓ {best['name']} (fans {best.get('nb_fan', 0)})")
        else:
            print(f"  {name:<24} ✗ ดาวน์โหลดไม่สำเร็จ")
            failed += 1

        time.sleep(PAUSE)

    print(f"  ดาวน์โหลดรูปศิลปิน {downloaded} | ข้าม {skipped} | พลาด {failed}")
    return downloaded, skipped, failed


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="ดึงปกเพลงและรูปศิลปิน")
    parser.add_argument("--cover-size", type=int, default=300, help="ขนาดปกที่ขอดาวน์โหลด (default 300)")
    parser.add_argument("--force", action="store_true", help="ดึงใหม่ทับของเดิม")
    parser.add_argument("--dry-run", action="store_true", help="ไม่โหลดไฟล์")
    parser.add_argument("--only-covers", action="store_true")
    parser.add_argument("--only-artists", action="store_true")
    args = parser.parse_args()

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"generated": None, "source": "iTunes (covers) + Deezer (artists)",
                "covers": {}, "artists": {}}
    if MANIFEST.exists():
        try:
            existing = json.loads(MANIFEST.read_text(encoding="utf-8"))
            manifest["covers"] = existing.get("covers", {})
            manifest["artists"] = existing.get("artists", {})
        except json.JSONDecodeError:
            pass

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    if not args.only_artists:
        print("\n=== ปกเพลง (iTunes) ===")
        fetch_covers(session, args.cover_size, args.force, args.dry_run, manifest)
    if not args.only_covers:
        print("\n=== รูปศิลปิน (Deezer) ===")
        fetch_artist_photos(session, args.force, args.dry_run, manifest)

    if args.dry_run:
        print("\n(dry-run: ไม่ได้เขียน manifest)")
        return 0

    from datetime import datetime

    manifest["generated"] = datetime.now().isoformat(timespec="seconds")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    covers = len(manifest["covers"])
    artists = len(manifest["artists"])
    total_mb = sum(p.stat().st_size for p in IMG_DIR.glob("*.jpg")) / 1024 / 1024
    print("\n" + "=" * 62)
    print(f"manifest: ปก {covers} ไฟล์ | รูปศิลปิน {artists} ไฟล์ | รวม {total_mb:.1f} MB")
    print(MANIFEST)
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
