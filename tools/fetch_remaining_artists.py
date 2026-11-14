"""
ดึงรูปศิลปิน 4 คนที่เหลือ (จับคู่ด้วยชื่อภาษาอังกฤษ/ไทยที่ตรวจแล้วว่าตรง)

  โจอี้ บอย         -> Deezer "Joey Boy"        (11,458 fans)
  ดาจิม            -> Deezer "Dajim"           (839 fans)
  Mike Piromporn  -> Deezer "ไมค์ ภิรมย์พร"      (340 fans)
  Fymme           -> Deezer "Fymme Bongkot"    (10 fans)

3 คนที่ยังไม่มีรูปน่าเชื่อถือ: Q Flure, Tai Orathai, Vhiew (ปล่อยเป็นไอคอนหัวคน)
"""
import io
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

from PIL import Image

ROOT = pathlib.Path(r"C:\Users\IMOS\Documents\Spi")
IMG_DIR = ROOT / "app" / "static" / "img"
MANIFEST = IMG_DIR / "manifest.json"
SEARCH = "https://api.deezer.com/search/artist"

# ชื่อใน DB -> คำค้นที่ตรวจแล้ว
TARGETS = {
    "โจอี้ บอย": "Joey Boy",
    "ดาจิม": "Dajim",
    "Mike Piromporn": "ไมค์ ภิรมย์พร",
    "Fymme": "Fymme Bongkot",
}


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "plern/1.0"})
    with urllib.request.urlopen(req, timeout=25) as res:
        return json.loads(res.read().decode())


def pick(term):
    data = get_json(f"{SEARCH}?q={urllib.parse.quote(term)}&limit=5").get("data", [])
    for item in data:
        pic = item.get("picture_xl") or ""
        if item.get("name", "").strip().lower() == term.strip().lower() and pic and "/artist//" not in pic:
            return item
    return None


def save_square(url, target):
    req = urllib.request.Request(url, headers={"User-Agent": "plern/1.0"})
    with urllib.request.urlopen(req, timeout=40) as res:
        raw = res.read()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img.crop((left, top, left + side, top + side)).resize((500, 500), Image.LANCZOS) \
        .save(target, "JPEG", quality=88, optimize=True)


def main():
    import pyodbc
    from app.config import Config
    sys.path.insert(0, str(ROOT))

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest.setdefault("artists", {})

    with pyodbc.connect(Config.CONNECTION_STRING) as conn:
        cur = conn.cursor()
        for db_name, term in TARGETS.items():
            cur.execute("SELECT ArtistID FROM dbo.Artist WHERE ArtistName = ?", db_name)
            row = cur.fetchone()
            if not row:
                print(f"  {db_name:<18} x ไม่พบใน DB")
                continue
            artist_id = row[0]
            item = pick(term)
            if not item:
                print(f"  {db_name:<18} x ไม่พบผู้สมัคร '{term}'")
                continue
            target = IMG_DIR / f"artist_{artist_id}.jpg"
            save_square(item["picture_xl"], target)
            manifest["artists"][str(artist_id)] = target.name
            print(f"  {db_name:<18} ok {item['name']} ({item.get('nb_fan', 0)} fans) -> {target.name}")
            time.sleep(0.5)

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("manifest artists:", len(manifest["artists"]))


if __name__ == "__main__":
    main()
