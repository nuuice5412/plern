"""
ดึงรูปศิลปินที่ยังขาด จาก Deezer (picture_xl 1000px) ย่อเป็น 500x500
อ่านรหัสศิลปินจาก docs/_artist_ids.json (สร้างด้วย tools/init_db.py หรือสคริปต์ resolve)

ใช้ได้กับ python ที่มี Pillow (ไม่ต้องมี pyodbc)
"""
import io
import json
import pathlib
import time
import urllib.parse
import urllib.request

from PIL import Image

ROOT = pathlib.Path(r"C:\Users\IMOS\Documents\Spi")
IMG_DIR = ROOT / "app" / "static" / "img"
MANIFEST = IMG_DIR / "manifest.json"
IDS = ROOT / "docs" / "_artist_ids.json"
SEARCH = "https://api.deezer.com/search/artist"
SIZE = 500

# ชื่อใน DB -> (คำค้นที่ต้องการ, ชื่อที่ใช้แสดงในรายงาน)
TERMS = {
    "แอ๊ด คาราบาว": "แอ๊ด คาราบาว",
    "Daft Punk": "Daft Punk",
    "Saran": "Saran",
    "ปั๊บ Potato": "ปั๊บ Potato",
    "Oat Pramote": "Oat Pramote",
    "Q Flure": "คิว ฟลัวร์",
    "ออม TELEx TELEXs": "Telex Telexs",
}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "plern/1.0"})
    with urllib.request.urlopen(req, timeout=25) as res:
        return json.loads(res.read().decode())


def pick(term: str) -> dict | None:
    data = get_json(f"{SEARCH}?q={urllib.parse.quote(term)}&limit=6").get("data", [])
    for item in data:                       # prefer an exact name match
        pic = item.get("picture_xl") or ""
        if item.get("name", "").strip().lower() == term.strip().lower() and pic and "/artist//" not in pic:
            return item
    for item in data:                       # otherwise the first one with a picture
        pic = item.get("picture_xl") or ""
        if pic and "/artist//" not in pic:
            return item
    return None


def save_square(url: str, target: pathlib.Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "plern/1.0"})
    with urllib.request.urlopen(req, timeout=40) as res:
        raw = res.read()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    side = min(img.size)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img.crop((left, top, left + side, top + side)).resize((SIZE, SIZE), Image.LANCZOS) \
        .save(target, "JPEG", quality=88, optimize=True)


def main() -> None:
    ids = json.loads(IDS.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest.setdefault("artists", {})

    report = []
    for name, artist_id in ids.items():
        term = TERMS.get(name, name)
        try:
            item = pick(term)
        except Exception as exc:
            print(f"  {name:<22} x {exc}")
            continue
        if not item:
            print(f"  {name:<22} x no candidate")
            continue

        target = IMG_DIR / f"artist_{artist_id}.jpg"
        try:
            save_square(item["picture_xl"], target)
        except Exception as exc:
            print(f"  {name:<22} x download: {exc}")
            continue

        manifest["artists"][str(artist_id)] = target.name
        report.append({
            "db_name": name,
            "deezer_name": item["name"],
            "fans": item.get("nb_fan", 0),
            "file": target.name,
            "exact_match": item["name"].strip().lower() == term.strip().lower(),
        })
        print(f"  {name:<22} ok {item['name']} (fans {item.get('nb_fan', 0)}) -> {target.name}")
        time.sleep(0.5)

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "docs" / "_artist_photo_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(report)}/7 photos · manifest now has {len(manifest['artists'])} artists")


if __name__ == "__main__":
    main()
