"""
fetch_previews.py - ดึงไฟล์พรีวิว 30 วินาทีจาก iTunes Search API มาใช้เป็นไฟล์เสียงของแอป

ทำไมใช้ iTunes Search API
  - เป็น preview ตัวเดียวกับที่ Apple Music ใช้ (30 วิ, AAC .m4a)
  - ไม่ต้องสมัคร key / ไม่ต้องมีบัญชีนักพัฒนา
  - ให้ metadata มาด้วย (ชื่อเพลงจริง, ศิลปิน, ปกอัลบั้ม, ความยาวจริง)

ข้อควรระวังด้านลิขสิทธิ์
  preview เหล่านี้ยังเป็นงานมีลิขสิทธิ์ ใบอนุญาตของ Apple อนุญาตให้ใช้เพื่อการ
  โปรโมต/สาธิตเท่านั้น -> เหมาะกับเดโมส่งอาจารย์ในเครื่อง
  ถ้าจะเผยแพร่สาธารณะ (GitHub public / deploy) ควรใช้เพลง CC0/CC-BY แทน
  เช่น Pixabay, Jamendo, Free Music Archive

วิธีใช้
    python tools/fetch_previews.py                    # ดึงทั้งหมดที่ยังไม่มีไฟล์
    python tools/fetch_previews.py --force            # ดึงใหม่ทับของเดิม
    python tools/fetch_previews.py --dry-run          # ดูผลจับคู่ ไม่โหลดไฟล์
    python tools/fetch_previews.py --only 1,3,5       # เฉพาะบางเพลง
    python tools/fetch_previews.py --country TH       # ร้านค้า iTunes (default TH)
    python tools/fetch_previews.py --convert-mp3      # แปลงเป็น mp3 ถ้ามี ffmpeg
    python tools/fetch_previews.py --min-score 0.6    # เข้มงวดการจับคู่ขึ้น

ไฟล์ที่ได้
    app/static/audio/song_<SongID>.m4a  (หรือ .mp3 ถ้าแปลง)
    app/static/audio/manifest.json      (บอกว่าเพลงไหนใช้ไฟล์อะไร)

เพลงที่จับคู่ไม่เจอ -> ไม่แตะไฟล์เดิม ปล่อยให้ player fallback ไป song_<id>.wav
ที่สร้างจาก tools/gen_audio.py
"""

from __future__ import annotations

import argparse
import difflib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import datetime

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIO_DIR = ROOT / "app" / "static" / "audio"
MANIFEST = AUDIO_DIR / "manifest.json"

ITUNES_URL = "https://itunes.apple.com/search"
USER_AGENT = "SpiMusicCourseProject/1.0 (educational demo)"
REQUEST_PAUSE = 2.0      # วินาทีระหว่างคำขอ (iTunes จำกัดราว 20 ครั้ง/นาที)
TIMEOUT = 25


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def norm(text: str) -> str:
    """ปรับข้อความให้เทียบกันได้: ตัดวงเล็บ/เครื่องหมาย/ช่องว่างซ้ำ และ lowercase"""
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[\(\)\[\]\{\}.,!?'\"·•\-–—/\\|&+]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def score_candidate(title: str, artist: str, candidate: dict) -> tuple[float, float, float]:
    """คืน (คะแนนรวม, คะแนนชื่อเพลง, คะแนนศิลปิน)"""
    cand_title = candidate.get("trackName", "")
    cand_artist = candidate.get("artistName", "")

    t = similarity(title, cand_title)
    # ถ้าชื่อเพลงที่ค้นไปปรากฏอยู่ในชื่อผลลัพธ์ ให้ถือว่าใกล้เคียงมาก
    if norm(title) and norm(title) in norm(cand_title):
        t = max(t, 0.92)

    a = similarity(artist, cand_artist)
    return (0.65 * t + 0.35 * a), t, a


def search_itunes(session: requests.Session, term: str, country: str, limit: int = 10) -> list[dict]:
    params = {
        "term": term,
        "media": "music",
        "entity": "song",
        "limit": limit,
        "country": country,
    }
    response = session.get(ITUNES_URL, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json().get("results", [])


def pick_best(title: str, artist: str, results: list[dict]) -> tuple[dict | None, tuple[float, float, float]]:
    best, best_score = None, (0.0, 0.0, 0.0)
    for candidate in results:
        if not candidate.get("previewUrl"):
            continue
        score = score_candidate(title, artist, candidate)
        if score[0] > best_score[0]:
            best, best_score = candidate, score
    return best, best_score


def ffmpeg_path() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ):
        if pathlib.Path(candidate).exists():
            return candidate
    return None


def convert_to_mp3(ffmpeg: str, source: pathlib.Path, bitrate: str = "128k") -> pathlib.Path | None:
    target = source.with_suffix(".mp3")
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-i", str(source),
        "-codec:a", "libmp3lame", "-b:a", bitrate,
        str(target),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or not target.exists():
        print(f"      [warn] แปลง mp3 ไม่สำเร็จ: {result.stderr.decode(errors='ignore')[:200]}")
        return None
    source.unlink(missing_ok=True)
    return target


def load_songs(only: set[int] | None) -> list[dict]:
    import pyodbc

    from app.config import Config

    with pyodbc.connect(Config.CONNECTION_STRING, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT SongID, SongTitle, MainArtistName, Duration
            FROM dbo.vw_SongDetail
            ORDER BY SongID
            """
        )
        rows = [
            {
                "SongID": row.SongID,
                "SongTitle": row.SongTitle,
                "Artist": row.MainArtistName,
                "Duration": row.Duration,
            }
            for row in cursor.fetchall()
        ]
    if only:
        rows = [r for r in rows if r["SongID"] in only]
    return rows


def load_manifest() -> dict:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"generated": None, "source": "iTunes Search API", "tracks": {}}


def save_manifest(manifest: dict) -> None:
    manifest["generated"] = datetime.now().isoformat(timespec="seconds")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="ดึงพรีวิว 30 วินาทีจาก iTunes")
    parser.add_argument("--country", default="TH", help="ร้านค้า iTunes เช่น TH, US (default TH)")
    parser.add_argument("--only", default="", help="ดึงเฉพาะ SongID เช่น 1,3,5")
    parser.add_argument("--force", action="store_true", help="โหลดใหม่ทับไฟล์เดิม")
    parser.add_argument("--dry-run", action="store_true", help="ไม่โหลดไฟล์ แค่ดูผลจับคู่")
    parser.add_argument("--convert-mp3", action="store_true", help="แปลงเป็น mp3 ถ้ามี ffmpeg")
    parser.add_argument("--min-score", type=float, default=0.68,
                        help="เกณฑ์ขั้นต่ำในการจับคู่ (default 0.68 — ต่ำกว่านี้เสี่ยงได้คนละเพลง)")
    args = parser.parse_args()

    only = {int(x) for x in re.findall(r"\d+", args.only)} if args.only else None

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    songs = load_songs(only)
    if not songs:
        print("ไม่พบเพลงในฐานข้อมูล (รัน tools/init_db.py ก่อน)")
        return 1

    print(f"เพลงที่จะประมวลผล: {len(songs)} เพลง | country={args.country} | เกณฑ์จับคู่ {args.min_score}\n")

    ffmpeg = ffmpeg_path() if args.convert_mp3 else None
    if args.convert_mp3 and not ffmpeg:
        print("[warn] ไม่พบ ffmpeg -> จะเก็บเป็น .m4a แทน (ไฟล์ใหญ่กว่า แต่เล่นได้)\n")

    manifest = load_manifest()
    manifest.setdefault("tracks", {})
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    matched = skipped = failed = 0

    for index, song in enumerate(songs, start=1):
        song_id = song["SongID"]
        title, artist = song["SongTitle"], song["Artist"]
        prefix = f"[{index:02d}/{len(songs)}] #{song_id:<3} {title} — {artist}"

        existing = list(AUDIO_DIR.glob(f"song_{song_id}.*"))
        existing_media = [p for p in existing if p.suffix.lower() in (".m4a", ".mp3")]
        if existing_media and not args.force:
            print(f"{prefix}\n        ข้าม (มีไฟล์อยู่แล้ว: {existing_media[0].name})")
            skipped += 1
            continue

        try:
            results = search_itunes(session, f"{title} {artist}", args.country)
            best, (total, title_score, artist_score) = pick_best(title, artist, results)

            # ลองค้นด้วยชื่อเพลงเดี่ยว ถ้ารอบแรกจับคู่ได้ไม่ดี
            if (best is None or total < args.min_score) and results is not None:
                time.sleep(REQUEST_PAUSE)
                results2 = search_itunes(session, title, args.country)
                best2, score2 = pick_best(title, artist, results2)
                if best2 is not None and score2[0] > (total if best else 0):
                    best, (total, title_score, artist_score) = best2, score2

            if best is None or total < args.min_score:
                print(f"{prefix}\n        ✗ จับคู่ไม่ได้ (คะแนนสูงสุด {total:.2f}) -> ใช้ไฟล์เดิมต่อ")
                failed += 1
                continue

            print(f"{prefix}")
            print(f"        ✓ {best['trackName']} — {best['artistName']}  "
                  f"(คะแนน {total:.2f})")

            if args.dry_run:
                matched += 1
                continue

            response = session.get(best["previewUrl"], timeout=TIMEOUT, stream=True)
            response.raise_for_status()
            extension = ".m4a"
            target = AUDIO_DIR / f"song_{song_id}{extension}"
            with target.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    handle.write(chunk)

            size_kb = target.stat().st_size / 1024
            if size_kb < 20:            # ไฟล์เล็กผิดปกติ = น่าจะไม่ใช่ไฟล์เสียง
                target.unlink(missing_ok=True)
                print(f"        ✗ ไฟล์ที่ได้เล็กผิดปกติ ({size_kb:.0f} KB)")
                failed += 1
                continue

            if ffmpeg:
                converted = convert_to_mp3(ffmpeg, target)
                if converted:
                    target = converted

            manifest["tracks"][str(song_id)] = {
                "file": target.name,
                "source": "itunes",
                "previewSeconds": 30,
                "matchedTitle": best.get("trackName"),
                "matchedArtist": best.get("artistName"),
                "collectionName": best.get("collectionName"),
                "itunesTrackId": best.get("trackId"),
                "previewUrl": best.get("previewUrl"),
            }
            save_manifest(manifest)     # เซฟทีละเพลง เผื่อถูก Ctrl+C กลางทาง
            print(f"        บันทึก {target.name} ({size_kb:.0f} KB)")
            matched += 1

        except requests.RequestException as exc:
            print(f"{prefix}\n        ✗ เน็ตเวิร์กผิดพลาด: {exc}")
            failed += 1
        except Exception as exc:        # noqa: BLE001 - เดินต่อแม้เพลงใดเพลงหนึ่งพัง
            print(f"{prefix}\n        ✗ ผิดพลาด: {exc}")
            failed += 1

        time.sleep(REQUEST_PAUSE)

    if not args.dry_run:
        save_manifest(manifest)

    # เพลงที่ไม่มีใน manifest -> ระบุชัดว่าใช้ไฟล์ .wav เดิม
    all_ids = {r["SongID"] for r in load_songs(None)}
    covered = {int(k) for k in manifest["tracks"]}
    fallback = sorted(all_ids - covered)

    print("\n" + "=" * 62)
    print(f"จับคู่สำเร็จ {matched} | ข้าม {skipped} | ไม่สำเร็จ {failed}")
    print(f"manifest: {MANIFEST}  (ครอบคลุม {len(covered)}/{len(all_ids)} เพลง)")
    if fallback:
        print(f"เพลงที่ยังใช้ไฟล์ .wav ที่สังเคราะห์ไว้: {fallback}")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
