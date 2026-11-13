"""
screenshot.py - เก็บภาพหน้าเว็บไว้ใช้ทำรายงาน/สไลด์

วิธีทำงาน
  - หน้าสาธารณะ  : เปิดด้วย Chrome headless ตรง ๆ
  - หน้าส่วนตัว  : ล็อกอินด้วย Flask test client -> ดัมพ์ HTML -> ชี้ path ของ
    static ไปที่ไฟล์ในเครื่อง -> เปิดด้วย Chrome headless (จึงไม่ต้องมี cookie)
  - ต้องรันเว็บไว้ก่อน: python run.py

ใช้
    python tools/screenshot.py
    python tools/screenshot.py --out docs/shots --width 1440 --height 1100
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# (ชื่อไฟล์, path, ต้องล็อกอินไหม)
PAGES = [
    ("home", "/", False),
    ("search", "/search?q=%E0%B8%9D%E0%B8%99", False),
    ("song", "/song/1", False),
    ("artist", "/artist/1", False),
    ("login", "/login", False),
    ("playlists", "/playlists", True),
    ("playlist", "/playlist/1", True),
    ("history", "/history", True),
]

LOGIN = {"identity": "demo", "password": "demo1234"}


def find_browser() -> str:
    for candidate in CHROME_CANDIDATES:
        if pathlib.Path(candidate).exists():
            return candidate
    sys.exit("ไม่พบ Chrome/Edge สำหรับจับภาพ")


def shoot(browser: str, url: str, outfile: pathlib.Path, size: tuple[int, int]) -> bool:
    profile = pathlib.Path(tempfile.mkdtemp(prefix="shot-prof-"))
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile}",
        f"--window-size={size[0]},{size[1]}",
        f"--screenshot={outfile}",
        url,
    ]
    if outfile.exists():
        outfile.unlink()
    subprocess.run(cmd, capture_output=True, timeout=120)
    return outfile.exists()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "docs" / "shots"))
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1100)
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    browser = find_browser()
    print(f"เบราว์เซอร์: {browser}")
    print(f"ปลายทาง   : {out_dir}\n")

    from app import create_app

    app = create_app()
    client = app.test_client()
    login_response = client.post("/login", data=LOGIN)
    static_uri = (ROOT / "app" / "static").as_uri() + "/"
    size = (args.width, args.height)

    ok_count = 0
    for name, path, needs_login in PAGES:
        target = out_dir / f"{name}.png"
        if needs_login:
            if login_response.status_code not in (301, 302):
                print(f"  [SKIP] {name}: ล็อกอินไม่สำเร็จ")
                continue
            html = client.get(path).get_data(as_text=True)
            # ให้เบราว์เซอร์โหลด CSS/JS จากไฟล์ในเครื่องแทน URL ของเซิร์ฟเวอร์
            html = html.replace("/static/", static_uri)
            tmp = pathlib.Path(tempfile.mkdtemp(prefix="shot-html-")) / f"{name}.html"
            tmp.write_text(html, encoding="utf-8")
            url = tmp.as_uri()
        else:
            url = args.base.rstrip("/") + path

        ok = shoot(browser, url, target, size)
        ok_count += 1 if ok else 0
        status = f"{target.stat().st_size // 1024} KB" if ok else "ล้มเหลว"
        print(f"  [{'OK' if ok else 'FAIL'}] {name:<10} {status}")

    print(f"\nได้ภาพ {ok_count}/{len(PAGES)} หน้า")
    return 0 if ok_count == len(PAGES) else 1


if __name__ == "__main__":
    sys.exit(main())
