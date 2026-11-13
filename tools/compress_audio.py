"""
compress_audio.py - แปลงไฟล์พรีวิวให้เป็น mp3 ที่คุณภาพ/ขนาดตามต้องการ

บริบท: iTunes ให้ไฟล์ 30 วินาทีมาเป็น AAC ~271 kbps (~1 MB/เพลง)
ถ้าเก็บต้นฉบับทุกเพลง 119 เพลงจะกิน ~116 MB จึงต้องเข้ารหัสใหม่

โหมดการทำงาน
  1) ปกติ            : แปลงไฟล์ .m4a ที่มีอยู่ในเครื่อง -> .mp3
  2) --refetch-original : ดาวน์โหลดต้นฉบับจาก previewUrl ใน audio/manifest.json
                         แล้วค่อยแปลง (ใช้ตอนอยาก "อัปเกรด" จากไฟล์ที่เคยบีบอัดแรงแล้ว
                         เช่น จาก 64 kbps เป็น 128 kbps — แปลงซ้ำจากของเดิมไม่ได้
                         เพราะคุณภาพที่เสียไปแล้วกู้คืนไม่ได้)

ใช้ PyAV (มี FFmpeg อยู่ในตัว) จึงไม่ต้องติดตั้ง ffmpeg แยก

ตัวอย่าง
    python tools/compress_audio.py --kbps 128                       # แปลงไฟล์ในเครื่อง
    python tools/compress_audio.py --kbps 128 --refetch-original    # ดึงต้นฉบับใหม่แล้วแปลง
    python tools/compress_audio.py --kbps 192 --refetch-original
    python tools/compress_audio.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "app" / "static" / "audio"
MANIFEST = AUDIO_DIR / "manifest.json"

USER_AGENT = "SpiMusicCourseProject/1.0 (educational demo)"
PAUSE = 0.6


def have_pyav() -> bool:
    try:
        import av  # noqa: F401
        return True
    except ImportError:
        return False


def transcode_with_pyav(source: pathlib.Path, target: pathlib.Path, kbps: int) -> bool:
    import av

    with av.open(str(source)) as in_container:
        in_stream = in_container.streams.audio[0]
        resampler = av.AudioResampler(format="s16p", layout="stereo", rate=in_stream.rate)

        with av.open(str(target), mode="w", format="mp3") as out_container:
            out_stream = out_container.add_stream("libmp3lame", rate=in_stream.rate)
            out_stream.bit_rate = kbps * 1000
            out_stream.layout = "stereo"

            for frame in in_container.decode(in_stream):
                for resampled in resampler.resample(frame):
                    for packet in out_stream.encode(resampled):
                        out_container.mux(packet)
            for packet in out_stream.encode(None):
                out_container.mux(packet)
    return target.exists() and target.stat().st_size > 1024


def transcode_with_ffmpeg(ffmpeg: str, source: pathlib.Path,
                          target: pathlib.Path, kbps: int) -> bool:
    result = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(source),
         "-codec:a", "libmp3lame", "-b:a", f"{kbps}k", str(target)],
        capture_output=True,
    )
    return result.returncode == 0 and target.exists() and target.stat().st_size > 1024


def duration_of(path: pathlib.Path) -> float:
    try:
        import av

        with av.open(str(path)) as container:
            return float(container.duration / 1_000_000) if container.duration else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def download_original(session, url: str, target: pathlib.Path) -> bool:
    try:
        response = session.get(url, timeout=30, stream=True)
        if response.status_code != 200:
            return False
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                handle.write(chunk)
    except Exception:  # noqa: BLE001 - เน็ตสะดุดให้ข้ามเพลงนี้
        return False
    return target.exists() and target.stat().st_size > 20 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description="แปลงพรีวิวเป็น mp3 ตาม bitrate ที่ต้องการ")
    parser.add_argument("--kbps", type=int, default=128, help="bitrate ของ mp3 (default 128)")
    parser.add_argument("--force", action="store_true", help="แปลงซ้ำแม้เป็น .mp3 แล้ว")
    parser.add_argument("--dry-run", action="store_true", help="แสดงผลเฉย ๆ ไม่แปลงไฟล์")
    parser.add_argument(
        "--refetch-original",
        action="store_true",
        help="ดาวน์โหลดต้นฉบับจาก previewUrl ก่อนแปลง (ใช้ตอนอัปเกรดคุณภาพ)",
    )
    args = parser.parse_args()

    if not MANIFEST.exists():
        print("ไม่พบ manifest.json — รัน tools/fetch_previews.py ก่อน")
        return 1

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tracks: dict = manifest.get("tracks", {})
    if not tracks:
        print("manifest ว่าง — ยังไม่มีไฟล์ให้แปลง")
        return 1

    use_pyav = have_pyav()
    ffmpeg = shutil.which("ffmpeg")
    if not use_pyav and not ffmpeg:
        print("ไม่พบทั้ง PyAV และ ffmpeg — ติดตั้งด้วย: pip install av")
        return 2
    engine = "PyAV" if use_pyav else f"ffmpeg ({ffmpeg})"

    session = None
    if args.refetch_original:
        import requests

        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT

    mode = "ดึงต้นฉบับใหม่จาก iTunes" if args.refetch_original else "ใช้ไฟล์ในเครื่อง"
    print(f"เครื่องมือ: {engine} | {args.kbps} kbps | {len(tracks)} เพลง | โหมด: {mode}\n")

    before = after = converted = skipped = failed = 0
    temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="audio-src-"))

    try:
        for index, (song_id, entry) in enumerate(
            sorted(tracks.items(), key=lambda kv: int(kv[0])), 1
        ):
            current = AUDIO_DIR / entry.get("file", "")
            old_size = current.stat().st_size if current.exists() else 0
            before += old_size

            # --- หาไฟล์ต้นทาง ---
            source: pathlib.Path | None = None
            temp_file: pathlib.Path | None = None

            if args.refetch_original:
                url = entry.get("previewUrl")
                if not url:
                    print(f"  [{index:03d}] #{song_id:<4} ไม่มี previewUrl — ข้าม")
                    failed += 1
                    after += old_size
                    continue
                temp_file = temp_dir / f"song_{song_id}.m4a"
                if not download_original(session, url, temp_file):
                    print(f"  [{index:03d}] #{song_id:<4} ดาวน์โหลดต้นฉบับไม่สำเร็จ")
                    failed += 1
                    after += old_size
                    continue
                source = temp_file
            else:
                if not current.exists():
                    print(f"  [{index:03d}] #{song_id:<4} ไม่พบไฟล์ {entry.get('file')}")
                    failed += 1
                    continue
                if current.suffix.lower() == ".mp3" and not args.force:
                    skipped += 1
                    after += old_size
                    continue
                source = current

            target = AUDIO_DIR / f"song_{song_id}.mp3"
            if args.dry_run:
                print(f"  [{index:03d}] #{song_id:<4} -> {target.name}")
                converted += 1
                after += old_size or 1
                if temp_file:
                    temp_file.unlink(missing_ok=True)
                continue

            ok = (transcode_with_pyav(source, target, args.kbps) if use_pyav
                  else transcode_with_ffmpeg(ffmpeg, source, target, args.kbps))
            if temp_file:
                temp_file.unlink(missing_ok=True)

            if not ok:
                print(f"  [{index:03d}] #{song_id:<4} แปลงไม่สำเร็จ")
                failed += 1
                after += old_size
                continue

            new_size = target.stat().st_size
            # ลบไฟล์เดิมถ้าคนละนามสกุล (เช่น .m4a เดิม)
            if current.exists() and current.suffix.lower() != ".mp3":
                current.unlink(missing_ok=True)

            entry["file"] = target.name
            entry["seconds"] = round(duration_of(target), 2)
            entry["bitrateKbps"] = args.kbps
            after += new_size
            converted += 1
            print(f"  [{index:03d}] #{song_id:<4} {old_size / 1024:6.0f} KB -> "
                  f"{new_size / 1024:6.0f} KB  ({target.name})")

            if args.refetch_original:
                time.sleep(PAUSE)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    manifest["tracks"] = tracks
    manifest["compressed"] = {"bitrateKbps": args.kbps, "engine": engine}
    if not args.dry_run:
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"แปลง {converted} | ข้าม {skipped} | พลาด {failed}")
    print(f"ขนาดรวม: {before / 1024 / 1024:.1f} MB -> {after / 1024 / 1024:.1f} MB")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
