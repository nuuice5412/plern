"""
fetch_originals.py - use the "original" audio files from iTunes without re-encoding

Context: tools/fetch_previews.py already downloaded the .m4a files (AAC ~271 kbps).
If you don't want any quality loss, you can use those files as-is — this script will
  1) Download the original from the previewUrl stored in audio/manifest.json
     (no new iTunes search -> exact file, no chance of a wrong match)
  2) Delete the .mp3 that was previously compressed for that song
  3) Update the manifest to point at the .m4a file

The size trade-off: ~1 MB per song (175 songs ≈ 175 MB)
If that is too heavy, use tools/compress_audio.py --kbps 128 instead (~82 MB)

Usage
    python tools/fetch_originals.py              # only songs that have no .m4a yet
    python tools/fetch_originals.py --force      # re-download everything
    python tools/fetch_originals.py --only 1,36  # only specific songs
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "app" / "static" / "audio"
MANIFEST = AUDIO_DIR / "manifest.json"

USER_AGENT = "SpiMusicCourseProject/1.0 (educational demo)"
PAUSE = 0.4
TIMEOUT = 45


def download(session: requests.Session, url: str, target: pathlib.Path) -> bool:
    response = session.get(url, timeout=TIMEOUT, stream=True)
    if response.status_code != 200:
        return False

    tmp = target.with_suffix(target.suffix + ".part")
    with tmp.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=128 * 1024):
            handle.write(chunk)

    if tmp.stat().st_size < 20 * 1024:      # too small to be a real audio file
        tmp.unlink(missing_ok=True)
        return False

    tmp.replace(target)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="เก็บไฟล์เสียงต้นฉบับจาก iTunes")
    parser.add_argument("--force", action="store_true", help="ดาวน์โหลดใหม่ทับของเดิม")
    parser.add_argument("--only", default="", help="เฉพาะ SongID เช่น 1,36,40")
    args = parser.parse_args()

    if not MANIFEST.exists():
        print("ไม่พบ audio/manifest.json — รัน tools/fetch_previews.py ก่อน")
        return 1

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tracks: dict = manifest.get("tracks", {})
    if not tracks:
        print("manifest ว่าง")
        return 1

    only = {int(x) for x in args.only.replace(" ", "").split(",") if x} if args.only else None
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    print(f"เป้าหมาย {len(tracks)} เพลง | โหมด {'ดาวน์โหลดใหม่ทั้งหมด' if args.force else 'เฉพาะที่ยังไม่มี'}\n")

    downloaded = skipped = failed = 0
    before_bytes = after_bytes = 0

    for index, song_id in enumerate(sorted(tracks, key=int), start=1):
        if only and int(song_id) not in only:
            continue

        entry = tracks[song_id]
        target = AUDIO_DIR / f"song_{song_id}.m4a"
        old_mp3 = AUDIO_DIR / f"song_{song_id}.mp3"
        before_bytes += old_mp3.stat().st_size if old_mp3.exists() else 0

        if target.exists() and not args.force:
            if old_mp3.exists():
                old_mp3.unlink()
            entry["file"] = target.name
            entry["bitrateKbps"] = "original"
            skipped += 1
            after_bytes += target.stat().st_size
            continue

        url = entry.get("previewUrl")
        if not url:
            print(f"  [{index:03d}] #{song_id:<4} ไม่มี previewUrl — ข้าม")
            failed += 1
            continue

        if not download(session, url, target):
            print(f"  [{index:03d}] #{song_id:<4} ดาวน์โหลดไม่สำเร็จ")
            failed += 1
            time.sleep(PAUSE)
            continue

        if old_mp3.exists():
            old_mp3.unlink()

        size = target.stat().st_size
        after_bytes += size
        downloaded += 1
        entry["file"] = target.name
        entry["bitrateKbps"] = "original"
        print(f"  [{index:03d}] #{song_id:<4} {size / 1024:6.0f} KB  ({target.name})")

        if downloaded % 20 == 0:            # save periodically in case of Ctrl+C
            manifest["tracks"] = tracks
            MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        time.sleep(PAUSE)

    manifest["tracks"] = tracks
    manifest["compressed"] = {"bitrateKbps": "original", "engine": "none (iTunes AAC)"}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    total_mb = sum((AUDIO_DIR / e["file"]).stat().st_size for e in tracks.values()
                   if (AUDIO_DIR / e["file"]).exists()) / 1024 / 1024

    print("\n" + "=" * 62)
    print(f"ดาวน์โหลด {downloaded} | มีอยู่แล้ว {skipped} | พลาด {failed}")
    print(f"ขนาดรวมไฟล์เสียงตอนนี้: {total_mb:.1f} MB")
    print(f"manifest: {MANIFEST}")
    print("=" * 62)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
