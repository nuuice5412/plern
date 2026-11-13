"""
fetch_fonts.py - download fonts (Google Fonts) and store them locally

Why not use <link> straight to fonts.googleapis.com:
  - the fonts vanish when the site is opened without internet (an exam room may have no wifi)
  - slower, because an extra DNS lookup is needed
  - keeping them locally makes the project self-contained, so the whole folder can be submitted

Fonts used: Inter (Latin) + Noto Sans Thai (Thai) — both are SIL Open Font License
and can be substituted legally (unlike Tidal's proprietary font)

How to use
    python tools/fetch_fonts.py
    python tools/fetch_fonts.py --weights 400,500,600,700,800
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "app" / "static" / "fonts"
CSS_OUT = ROOT / "app" / "static" / "css" / "fonts.css"

CSS_URL = "https://fonts.googleapis.com/css2"
# a modern UA -> Google returns woff2 files (the smallest)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# keep only the subsets actually used (Thai + Latin) to reduce size
KEEP_SUBSETS = {"thai", "latin", "latin-ext"}


def main() -> int:
    parser = argparse.ArgumentParser(description="ดาวน์โหลดฟอนต์มาเก็บในเครื่อง")
    parser.add_argument("--weights", default="400,500,600,700,800")
    parser.add_argument("--families", default="Inter,Noto Sans Thai")
    args = parser.parse_args()

    weights = ";".join(w.strip() for w in args.weights.split(",") if w.strip())
    query = "&".join(
        f"family={family.replace(' ', '+')}:wght@{weights}"
        for family in args.families.split(",")
    )
    url = f"{CSS_URL}?{query}&display=swap"

    print(f"ขอ CSS จาก Google Fonts ({len(args.weights.split(','))} น้ำหนัก ต่อ família)")
    response = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    response.raise_for_status()
    css = response.text

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    CSS_OUT.parent.mkdir(parents=True, exist_ok=True)

    # split out @font-face blocks together with their subset comment, e.g. /* thai */
    blocks = re.findall(r"(/\*\s*([\w-]+)\s*\*/\s*@font-face\s*\{[^}]*\})", css)
    if not blocks:
        blocks = [("", "all", m) for m in re.findall(r"(@font-face\s*\{[^}]*\})", css)]

    kept: list[str] = []
    downloaded: dict[str, str] = {}

    for block, subset, _full in [(b[0], b[1], b[0]) for b in blocks]:
        if subset not in KEEP_SUBSETS and subset != "all":
            continue

        url_match = re.search(r"url\((https://[^)]+)\)", block)
        if not url_match:
            continue
        remote = url_match.group(1)

        filename = remote.rsplit("/", 1)[-1]
        if not filename.endswith(".woff2"):
            filename += ".woff2"
        local = FONT_DIR / filename

        if filename not in downloaded:
            if not local.exists():
                data = requests.get(remote, headers={"User-Agent": UA}, timeout=30)
                data.raise_for_status()
                local.write_bytes(data.content)
                print(f"  โหลด {filename} ({len(data.content) / 1024:.0f} KB)")
            downloaded[filename] = filename

        kept.append(block.replace(remote, f"../fonts/{filename}"))

    header = (
        "/* สร้างโดย tools/fetch_fonts.py — ฟอนต์เก็บในเครื่อง (SIL Open Font License)\n"
        "   Inter (Latin) + Noto Sans Thai (ไทย) */\n\n"
    )
    CSS_OUT.write_text(header + "\n\n".join(kept) + "\n", encoding="utf-8")

    total = sum(p.stat().st_size for p in FONT_DIR.glob("*.woff2")) / 1024
    print(f"\n@font-face {len(kept)} บล็อก | ไฟล์ฟอนต์ {len(downloaded)} ไฟล์ | รวม {total:.0f} KB")
    print(f"CSS: {CSS_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
