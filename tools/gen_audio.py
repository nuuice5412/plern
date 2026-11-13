"""
gen_audio.py - generate sample audio files (.wav) for every song in the SONG table

Why this exists: this project is a music streaming app. If pressing play gives no demo
audio to hear, the demo falls flat, so we synthesize it ourselves with Python's standard
library (nothing downloaded, no licensing issues, and repeatable on any machine).

The file name is tied to SongID: app/static/audio/song_<SongID>.wav
=> no need to add an AudioUrl column to SONG (schema still matches the original ER)

Usage
    python tools/gen_audio.py            # generate all songs (24 by default)
    python tools/gen_audio.py --count 24
    python tools/gen_audio.py --force    # overwrite existing files
"""

from __future__ import annotations

import argparse
import math
import pathlib
import struct
import wave

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "app" / "static" / "audio"

SAMPLE_RATE = 16_000        # 16 kHz mono is plenty for a demo (small files)
DURATION = 10.0             # seconds per song

# 4 chords per song (semitone offset from the root) — 3 progressions cycle through
PROGRESSIONS = [
    [(0, 4, 7), (7, 11, 14), (9, 12, 16), (5, 9, 12)],      # I - V - vi - IV
    [(0, 3, 7), (8, 12, 15), (3, 7, 10), (10, 14, 17)],     # i - VI - III - VII
    [(0, 4, 7), (9, 12, 16), (5, 9, 12), (7, 11, 14)],      # I - vi - IV - V
    [(0, 5, 7), (5, 9, 12), (0, 4, 7), (7, 12, 16)],        # sus / Open
]


def midi_to_freq(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def render_note(buf: list[float], start_sec: float, freq: float, dur: float,
                amp: float, decay: float = 2.2) -> None:
    """Mix one note (sine + a little harmonic) into the buffer, additively"""
    start = int(start_sec * SAMPLE_RATE)
    n = min(int(dur * SAMPLE_RATE), len(buf) - start)
    if n <= 0:
        return

    w1 = 2.0 * math.pi * freq / SAMPLE_RATE
    w2 = 2.0 * math.pi * freq * 2.0 / SAMPLE_RATE
    attack = max(1, int(0.012 * SAMPLE_RATE))
    release = max(1, int(0.10 * SAMPLE_RATE))

    for k in range(n):
        if k < attack:
            env = k / attack
        elif k > n - release:
            env = max(0.0, (n - k) / release)
        else:
            env = 1.0
        env *= math.exp(-decay * k / n)             # fade out like a pluck
        s = math.sin(w1 * k) + 0.22 * math.sin(w2 * k)
        buf[start + k] += amp * env * s


def build_song(song_id: int) -> list[float]:
    total = int(DURATION * SAMPLE_RATE)
    buf = [0.0] * total

    # a different key per song, so they sound distinct
    root = 45 + (song_id * 5) % 12                    # A2 .. G#3
    prog = PROGRESSIONS[(song_id - 1) % len(PROGRESSIONS)]
    chord_dur = DURATION / len(prog)

    for idx, chord in enumerate(prog):
        t0 = idx * chord_dur
        # --- pad: sustained chord notes ---
        for semi in chord:
            render_note(buf, t0, midi_to_freq(root + semi), chord_dur * 0.98,
                        amp=0.16, decay=0.35)
        # --- bass: chord root one octave down ---
        render_note(buf, t0, midi_to_freq(root - 12 + chord[0]), chord_dur * 0.5,
                    amp=0.22, decay=1.2)
        # --- melody: chord arpeggio one octave up ---
        step = chord_dur / 4.0
        arp = [chord[0], chord[1], chord[2], chord[1] + 12]
        for j, semi in enumerate(arp):
            render_note(buf, t0 + j * step, midi_to_freq(root + semi + 12),
                        step * 0.95, amp=0.11, decay=3.0)

    # normalize against clipping + fade in/out at both ends
    peak = max((abs(x) for x in buf), default=1.0) or 1.0
    gain = 0.85 / peak
    fade = int(0.25 * SAMPLE_RATE)
    for i in range(total):
        v = buf[i] * gain
        if i < fade:
            v *= i / fade
        elif i > total - fade:
            v *= (total - i) / fade
        buf[i] = v
    return buf


def write_wav(path: pathlib.Path, samples: list[float]) -> None:
    frames = bytearray()
    for s in samples:
        v = int(max(-1.0, min(1.0, s)) * 32767)
        frames += struct.pack("<h", v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(frames))


def main() -> int:
    parser = argparse.ArgumentParser(description="สร้างไฟล์เสียงตัวอย่างสำหรับทุกเพลง")
    parser.add_argument("--count", type=int, default=24, help="จำนวนเพลง (SongID 1..N)")
    parser.add_argument("--force", action="store_true", help="เขียนทับไฟล์ที่มีอยู่")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    created = skipped = 0

    for song_id in range(1, args.count + 1):
        path = OUT_DIR / f"song_{song_id}.wav"
        if path.exists() and not args.force:
            skipped += 1
            continue
        samples = build_song(song_id)
        write_wav(path, samples)
        created += 1
        print(f"  song_{song_id}.wav  {path.stat().st_size / 1024:.0f} KB")

    total_kb = sum(p.stat().st_size for p in OUT_DIR.glob("song_*.wav")) / 1024
    print(f"\nสร้างใหม่ {created} ไฟล์, ข้าม {skipped} ไฟล์")
    print(f"รวมทั้งหมด {total_kb / 1024:.1f} MB ที่ {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
