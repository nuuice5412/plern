"""
sync_catalog.py - adds artists/songs from the iTunes Search API to the database

Two working modes
  1) search mode (default)    : take the top-N popular results per artist
  2) --full mode             : pull the artist's "entire discography" (lookup by artistId)

The returned data (track titles, duration, release date, featured artists) comes straight from iTunes,
so tools/fetch_previews.py is guaranteed to find the 30-second preview with a full score.

Usage
    python tools/sync_catalog.py --list-artists          # show the default artist list
    python tools/sync_catalog.py --dry-run               # show what would be added, no DB writes
    python tools/sync_catalog.py                         # add from the default list
    python tools/sync_catalog.py --artists "PURPEECH,Only Monday" --full
    python tools/sync_catalog.py --artists "PURPEECH" --full --include-variants
    python tools/sync_catalog.py --per-artist 8 --plays 8
"""

from __future__ import annotations

import argparse
import difflib
import pathlib
import re
import sys
import time
import unicodedata

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ITUNES_SEARCH = "https://itunes.apple.com/search"
ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
USER_AGENT = "SpiMusicCourseProject/1.0 (educational demo)"
PAUSE = 2.0
TIMEOUT = 30

# default artist set: 10 Thai + 6 international (add or remove freely)
DEFAULT_ARTISTS: list[tuple[str, str]] = [
    ("Tattoo Colour", "TH"),
    ("Polycat", "TH"),
    ("Getsunova", "TH"),
    ("Potato", "TH"),
    ("Big Ass", "TH"),
    ("Slot Machine", "TH"),
    ("Paradox", "TH"),
    ("The Toys", "TH"),
    ("Jeff Satur", "TH"),
    ("Bowkylion", "TH"),
    ("The Weeknd", "US"),
    ("Dua Lipa", "UK"),
    ("Coldplay", "UK"),
    ("Bruno Mars", "US"),
    ("Billie Eilish", "US"),
    ("Laufey", "IS"),
]

# words that mark a result as not the original song (karaoke/cover/tribute)
NOISE_WORDS = (
    "karaoke", "cover version", "tribute", "made famous", "originally performed",
    "instrumental", "backing track", "in the style of", "sing along",
)

# words that mark another version of the same song (skippable unless --include-variants)
VARIANT_WORDS = ("live", "acoustic", "session", "remix", "demo", "sped up", "slowed")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[\(\)\[\]\{\}.,!?'\"·•\-–—/\\|&+]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def artist_matches(candidate: str, wanted: str) -> bool:
    a, b = norm(candidate), norm(wanted)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def is_noise(result: dict) -> bool:
    haystack = " ".join(
        str(result.get(key) or "") for key in ("trackName", "collectionName", "artistName")
    ).lower()
    return any(word in haystack for word in NOISE_WORDS)


def is_variant(result: dict) -> bool:
    haystack = f"{result.get('trackName') or ''} {result.get('collectionName') or ''}".lower()
    return any(word in haystack for word in VARIANT_WORDS)


def title_key(title: str) -> tuple[str, str]:
    """
    Split a song title into (base title, version tag) to drop "the same recording" coming from
    both a single and an album, while still keeping differently named versions (e.g. (Live), (Acoustic))

        'ทิ้งไป'                  -> ('ทิ้งไป', '')
        'หากจะเพียงขอ (Sincare)' -> ('หากจะเพียงขอ', 'sincare')
    """
    brackets = re.findall(r"[\(\[]([^\)\]]*)[\)\]]", title or "")
    base = re.sub(r"[\(\[]\s*[^\)\]]*[\)\]]", " ", title or "")
    base = re.sub(r"\s*(?:feat\.|ft\.).*$", "", base, flags=re.IGNORECASE)
    return norm(base), norm(" ".join(brackets))


# ชื่อวงที่เป็นศิลปินคู่/วงดนตรี — ห้ามแยกที่ "&" (เช่น Whal & Dolph)
KNOWN_GROUPS = {
    "whal & dolph",
    "simon & garfunkel",
    "telex telexs",
}


def split_artists(artist_name: str) -> list[str]:
    """'The Weeknd, JENNIE & Lily Rose Depp' -> 3 names"""
    whole = (artist_name or "").strip()
    if whole.lower() in KNOWN_GROUPS:
        return [whole]
    parts = re.split(r"\s*(?:,|&|\bfeat\.|\bft\.|\sx\s)\s*", whole)
    return [p.strip() for p in parts if p.strip()]


def feat_from_title(title: str) -> list[str]:
    """Extract featured artist names from '(feat. X)' or '[feat. X]' in the song title."""
    found = re.findall(r"[\(\[]\s*(?:feat\.|ft\.)\s*([^\)\]]+)", title or "", flags=re.IGNORECASE)
    names = []
    for chunk in found:
        names.extend(split_artists(chunk))
    return names


# ---------------------------------------------------------------------------
# iTunes
# ---------------------------------------------------------------------------
def resolve_artist_id(session: requests.Session, name: str, country: str) -> int | None:
    response = session.get(
        ITUNES_SEARCH,
        params={"term": name, "media": "music", "entity": "musicArtist", "limit": 10,
                "country": country},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    best, best_score = None, 0.0
    for item in response.json().get("results", []):
        score = difflib.SequenceMatcher(None, norm(item.get("artistName", "")), norm(name)).ratio()
        if score > best_score:
            best, best_score = item, score
    if best is None or best_score < 0.85:
        return None
    return int(best["artistId"])


def fetch_catalog(session: requests.Session, artist_id: int, country: str) -> list[dict]:
    response = session.get(
        ITUNES_LOOKUP,
        params={"id": artist_id, "entity": "song", "limit": 200, "country": country},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return [
        item for item in response.json().get("results", [])
        if item.get("wrapperType") == "track" and item.get("kind") == "song"
    ]


def fetch_search_songs(session: requests.Session, artist: str, country: str,
                       per_artist: int) -> list[dict]:
    response = session.get(
        ITUNES_SEARCH,
        params={"term": artist, "media": "music", "entity": "song", "limit": 50,
                "country": country},
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    picked: list[dict] = []
    seen_titles: set[str] = set()
    for item in response.json().get("results", []):
        if not item.get("previewUrl") or not item.get("trackName"):
            continue
        if not artist_matches(item.get("artistName", ""), artist):
            continue
        if is_noise(item):
            continue
        key = norm(item["trackName"])
        if key in seen_titles:
            continue
        seen_titles.add(key)
        picked.append(item)
        if len(picked) >= per_artist:
            break
    return picked


# ---------------------------------------------------------------------------
# database
# ---------------------------------------------------------------------------
def get_conn():
    import pyodbc

    from app.config import Config

    return pyodbc.connect(Config.CONNECTION_STRING, timeout=15, autocommit=True)


def ensure_artist(cursor, name: str, country: str) -> int:
    cursor.execute("SELECT ArtistID FROM dbo.Artist WHERE ArtistName = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute(
        "INSERT INTO dbo.Artist (ArtistName, Country, Bio) OUTPUT INSERTED.ArtistID VALUES (?, ?, NULL)",
        (name, country),
    )
    return int(cursor.fetchone()[0])


def song_exists(cursor, title: str, artist_id: int) -> bool:
    cursor.execute(
        "SELECT 1 FROM dbo.Song AS s "
        "JOIN dbo.Song_Artist_Role AS sar ON sar.SongID = s.SongID "
        "WHERE s.SongTitle = ? AND sar.ArtistID = ?",
        (title, artist_id),
    )
    return cursor.fetchone() is not None


def insert_song_row(cursor, item: dict) -> int:
    title = item["trackName"]
    duration = max(1, int(round((item.get("trackTimeMillis") or 0) / 1000)))
    released = (item.get("releaseDate") or "")[:10] or None
    cursor.execute(
        "INSERT INTO dbo.Song (SongTitle, Duration, PlayCount, Released_Date) "
        "OUTPUT INSERTED.SongID VALUES (?, ?, 0, ?)",
        (title, duration, released),
    )
    return int(cursor.fetchone()[0])


def link_roles(cursor, song_id: int, primary_id: int, featured_ids: list[int]) -> None:
    cursor.execute("SELECT RoleID, [Role] FROM dbo.[Role]")
    roles = {name: rid for rid, name in cursor.fetchall()}

    for role_name in ("Singer", "Composer", "Producer"):
        if role_name in roles:
            cursor.execute(
                "INSERT INTO dbo.Song_Artist_Role (SongID, ArtistID, RoleID) VALUES (?, ?, ?)",
                (song_id, primary_id, roles[role_name]),
            )
    for artist_id in featured_ids:
        if "Featured" in roles and artist_id != primary_id:
            cursor.execute(
                "SELECT 1 FROM dbo.Song_Artist_Role WHERE SongID = ? AND ArtistID = ? AND RoleID = ?",
                (song_id, artist_id, roles["Featured"]),
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO dbo.Song_Artist_Role (SongID, ArtistID, RoleID) VALUES (?, ?, ?)",
                    (song_id, artist_id, roles["Featured"]),
                )


def seed_plays(cursor, song_id: int, plays: int) -> None:
    cursor.execute("SELECT UserID FROM dbo.[User] ORDER BY UserID")
    users = [row[0] for row in cursor.fetchall()]
    if not users:
        return
    for index in range(plays):
        hours_ago = (song_id * 7 + index * 13) % 480
        cursor.execute(
            "INSERT INTO dbo.History (Played_At, UserID, SongID) "
            "VALUES (DATEADD(HOUR, ?, SYSDATETIME()), ?, ?)",
            (-hours_ago, users[index % len(users)], song_id),
        )


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="เพิ่มศิลปิน/เพลงจาก iTunes เข้าฐานข้อมูล")
    parser.add_argument("--artists", default="", help='รายชื่อศิลปินคั่นด้วย , เช่น "Palmy,Laufey"')
    parser.add_argument("--artists-file", help="ไฟล์รายชื่อศิลปิน (บรรทัดละคน, ใส่ :ประเทศ ได้)")
    parser.add_argument("--per-artist", type=int, default=6, help="จำนวนเพลงต่อศิลปิน (โหมดค้นหา)")
    parser.add_argument("--full", action="store_true", help="ดึงทั้งดิสโคกราฟีของศิลปิน")
    parser.add_argument("--include-variants", action="store_true",
                        help="รวมเวอร์ชัน Live/Acoustic/Remix ด้วย (ใช้กับ --full)")
    parser.add_argument("--plays", type=int, default=6, help="สร้างประวัติฟังกี่ครั้งต่อเพลงใหม่")
    parser.add_argument("--country", default="TH", help="ร้านค้า iTunes (default TH)")
    parser.add_argument("--dry-run", action="store_true", help="ไม่เขียนฐานข้อมูล")
    parser.add_argument("--list-artists", action="store_true", help="แสดงรายชื่อศิลปินชุดเริ่มต้น")
    args = parser.parse_args()

    if args.list_artists:
        print("ศิลปินชุดเริ่มต้น (ใช้ --artists เพื่อระบุเอง):")
        for name, country in DEFAULT_ARTISTS:
            print(f"  - {name} ({country})")
        return 0

    targets: list[tuple[str, str]] = []
    if args.artists:
        for raw in args.artists.split(","):
            if raw.strip():
                targets.append((raw.strip(), args.country))
    if args.artists_file:
        for line in pathlib.Path(args.artists_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                name, country = line.rsplit(":", 1)
                targets.append((name.strip(), country.strip()))
            else:
                targets.append((line, args.country))
    if not targets:
        targets = list(DEFAULT_ARTISTS)

    mode = "ทั้งดิสโคกราฟี" if args.full else f"top {args.per_artist} เพลง"
    print(f"ศิลปิน {len(targets)} คน | โหมด {mode} | ประเทศ {args.country} | "
          f"{'DRY-RUN' if args.dry_run else 'เขียนฐานข้อมูลจริง'}\n")

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    conn = None if args.dry_run else get_conn()
    cursor = conn.cursor() if conn else None

    added = skipped = failed = new_artists = 0

    for index, (artist_name, country) in enumerate(targets, start=1):
        print(f"[{index:02d}/{len(targets)}] {artist_name}")
        try:
            if args.full:
                artist_id = resolve_artist_id(session, artist_name, country)
                if artist_id is None:
                    print("        ✗ ไม่พบศิลปินนี้ใน iTunes")
                    failed += 1
                    time.sleep(PAUSE)
                    continue
                time.sleep(PAUSE)
                catalog = fetch_catalog(session, artist_id, country)
            else:
                catalog = fetch_search_songs(session, artist_name, country, args.per_artist)
        except requests.RequestException as exc:
            print(f"        ✗ เน็ตเวิร์กผิดพลาด: {exc}")
            failed += 1
            time.sleep(PAUSE)
            continue

        # filter out duplicate songs (the same recording bundled in both an album and a single)
        picked: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in catalog:
            if not item.get("previewUrl") or not item.get("trackName"):
                continue
            if is_noise(item):
                continue
            if args.full and not args.include_variants and is_variant(item):
                continue
            key = title_key(item["trackName"])
            if key in seen:
                continue
            seen.add(key)
            picked.append(item)

        print(f"        พบ {len(catalog)} แทร็ก -> เลือก {len(picked)} เพลง")

        if args.dry_run:
            for item in picked:
                mins = int(round((item.get("trackTimeMillis") or 0) / 1000))
                print(f"          + {item['trackName'][:50]:<52} {mins // 60}:{mins % 60:02d}"
                      f"  [{item.get('artistName')}]")
            added += len(picked)
            time.sleep(PAUSE)
            continue

        for item in picked:
            # primary/featured artists from artistName + feat. in the title
            names = split_artists(item.get("artistName") or artist_name)
            if not names:
                names = [artist_name]
            primary_name = names[0]
            guest_names = names[1:] + feat_from_title(item["trackName"])

            primary_id = ensure_artist(cursor, primary_name, country)
            guest_ids = [ensure_artist(cursor, n, country) for n in guest_names if n]

            if song_exists(cursor, item["trackName"], primary_id):
                skipped += 1
                continue

            song_id = insert_song_row(cursor, item)
            link_roles(cursor, song_id, primary_id, guest_ids)
            if args.plays:
                seed_plays(cursor, song_id, args.plays)
            added += 1
            mins = int(round((item.get("trackTimeMillis") or 0) / 1000))
            guests = f" (feat. {', '.join(guest_names)})" if guest_names else ""
            print(f"          + #{song_id:<4} {item['trackName'][:44]:<46} "
                  f"{mins // 60}:{mins % 60:02d}{guests}")

        time.sleep(PAUSE)

    print("\n" + "=" * 66)
    print(f"เพิ่มเพลงใหม่ {added} | มีอยู่แล้ว {skipped} | พลาด {failed}")
    if conn:
        cursor.execute("SELECT COUNT(*) FROM dbo.Song")
        total_songs = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM dbo.Artist")
        total_artists = cursor.fetchone()[0]
        print(f"ในฐานข้อมูลตอนนี้: {total_songs} เพลง / {total_artists} ศิลปิน")
        print("\nขั้นต่อไป: python tools/fetch_previews.py")
    print("=" * 66)

    if conn:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
