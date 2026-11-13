"""
smoke_test.py - ทดสอบเว็บแอปแบบ end-to-end ผ่าน HTTP

ต้องรันเว็บไว้ก่อน (python run.py) แล้วสั่ง
    python tools/smoke_test.py
    python tools/smoke_test.py --base http://127.0.0.1:5000

ตรวจว่า: หน้าเว็บหลักเปิดได้, ค้นหาได้, login ได้, บันทึกการฟังแล้ว PlayCount
เพิ่มขึ้นจริง, สร้าง/เพิ่ม/ลบเพลงในเพลย์ลิสต์ผ่าน stored procedure ได้,
สมัครสมาชิกได้, และหน้า error ทำงานถูกต้อง
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

import requests

# ให้ import app.config ได้ไม่ว่าจะรันจากโฟลเดอร์ไหน
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, bool, str]] = []

# ---- ข้อมูลอ้างอิงจาก db/02_seed.sql (แก้ที่นี่ที่เดียวถ้าเปลี่ยน seed) ----
SAMPLE_SONG_ID = 1
SAMPLE_SONG_TITLE = "หลุมอากาศ"
SAMPLE_ARTIST = "Palmy"
SEARCH_TERM = "รัก"
SEARCH_EXPECT = "โปรดเถิดรัก"
PLAYLIST_TEST_SONG = 5
PLAYLIST_TEST_SONG_TITLE = "โปรดเถิดรัก"


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, bool(condition), detail))
    mark = PASS if condition else FAIL
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not condition else ""))


def read_email_code(email: str) -> str | None:
    """อ่านรหัส OTP ล่าสุดของอีเมลนี้จากฐานข้อมูล (ใช้ตรวจในเทสต์)"""
    import pyodbc

    from app.config import Config

    with pyodbc.connect(Config.CONNECTION_STRING) as conn:
        cur = conn.cursor()
        cur.execute("SELECT Code FROM dbo.EmailCode WHERE Email = ?", (email,))
        row = cur.fetchone()
        return row[0] if row else None


def cleanup_test_data() -> str:
    """ลบเพลย์ลิสต์/ผู้ใช้ที่ smoke test สร้างขึ้น ไม่ให้รกฐานข้อมูลจริง"""
    import pyodbc

    from app.config import Config

    with pyodbc.connect(Config.CONNECTION_STRING, autocommit=True) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.EmailCode WHERE Email LIKE 'smoke%'")
        cur.execute("DELETE FROM dbo.Playlist WHERE PLname LIKE N'ทดสอบ[_]%'")
        playlists = cur.rowcount
        cur.execute(
            "DELETE FROM dbo.History WHERE UserID IN "
            "(SELECT UserID FROM dbo.[User] WHERE Username LIKE 'smoke%')"
        )
        cur.execute(
            "DELETE FROM dbo.Playlist WHERE UserID IN "
            "(SELECT UserID FROM dbo.[User] WHERE Username LIKE 'smoke%')"
        )
        cur.execute("DELETE FROM dbo.[User] WHERE Username LIKE 'smoke%'")
        users = cur.rowcount
    return f"ลบเพลย์ลิสต์ {playlists} รายการ, ผู้ใช้ทดสอบ {users} คน"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    session = requests.Session()
    session.headers["User-Agent"] = "dsh-smoke-test"

    # 1) ต้องเข้าสู่ระบบก่อนสำหรับหน้าส่วนตัว
    print("\n[1] หน้าเว็บสาธารณะ")
    r = session.get(base + "/", timeout=15)
    check("GET / ตอบ 200", r.status_code == 200, str(r.status_code))
    check("หน้าแรกมีหัวข้อเพลงยอดนิยม", "เพลงยอดนิยม" in r.text)
    check("หน้าแรกมีรายชื่อศิลปิน", SAMPLE_ARTIST in r.text)

    r = session.get(base + "/search", params={"q": SEARCH_TERM}, timeout=15)
    check(f"GET /search?q={SEARCH_TERM} ตอบ 200", r.status_code == 200, str(r.status_code))
    check(f"ค้นหาเจอเพลง '{SEARCH_EXPECT}'", SEARCH_EXPECT in r.text)

    r = session.get(base + f"/song/{SAMPLE_SONG_ID}", timeout=15)
    check(f"GET /song/{SAMPLE_SONG_ID} ตอบ 200", r.status_code == 200, str(r.status_code))
    check("หน้ารายละเอียดเพลงมีชื่อเพลง", SAMPLE_SONG_TITLE in r.text)
    check("หน้ารายละเอียดเพลงแสดงบทบาทศิลปิน", "Singer" in r.text)

    r = session.get(base + "/artist/1", timeout=15)
    check("GET /artist/1 ตอบ 200", r.status_code == 200, str(r.status_code))
    check("หน้าศิลปินแสดงชื่อศิลปิน", SAMPLE_ARTIST in r.text)

    # หน้า "ดูทั้งหมด" ที่กดจากปุ่มบนหน้าแรก
    r = session.get(base + "/songs", timeout=15)
    check("GET /songs (เพลงทั้งหมด) ตอบ 200", r.status_code == 200, str(r.status_code))
    check("หน้า /songs มีรายการเพลง", r.text.count('class="track"') >= 20,
          str(r.text.count('class="track"')))

    # ปุ่ม "เล่นเพลงยอดนิยม" ต้องหาการ์ดเจอ (เคยพังตอนเปลี่ยนจากตารางเป็นการ์ด)
    r = session.get(base + "/", timeout=15)
    check("หน้าแรกมีปุ่มเล่นทั้งรายการ", "data-play-list" in r.text)
    check("การ์ดเพลงมี data-id สำหรับเล่น", r.text.count('class="rail-card"') >= 5
          and 'data-id=' in r.text)

    r = session.get(base + "/artists", timeout=15)
    check("GET /artists (ศิลปินทั้งหมด) ตอบ 200", r.status_code == 200, str(r.status_code))
    check("หน้า /artists มีการ์ดศิลปิน", r.text.count('class="artist-card"') >= 10,
          str(r.text.count('class="artist-card"')))

    # regression: เครดิตศิลปินคอลแลบต้องแสดงครบ (เคยขาดหายเพราะใช้ artistName ตัวแรก)
    r = session.get(base + "/song/68", timeout=15)
    check("เพลงคอลแลบแสดงศิลปินครบ (PUN, The Toys)",
          r.status_code == 200 and "PUN" in r.text and "The Toys" in r.text,
          str(r.status_code))
    r = session.get(base + "/song/101", timeout=15)
    check("เพลงที่มี feat. แสดงศิลปินรับเชิญด้วย", "Khalid" in r.text, str(r.status_code))

    # API ที่หน้าจอเต็มใช้ดึงเครดิต (แท็บ "เครดิต" ไม่ต้องออกจากหน้า)
    r = session.get(base + "/api/song/68", timeout=15)
    check("GET /api/song/68 ตอบ 200", r.status_code == 200, str(r.status_code))
    payload = r.json() if r.status_code == 200 else {}
    roles = {item.get("Role") for item in payload.get("credits", [])}
    check("API เครดิตคืนบทบาทของศิลปินครบ", {"Singer", "Composer", "Producer"} <= roles,
          str(sorted(roles)))
    check("API เครดิตมีชื่อศิลปินและปีที่ออก",
          bool(payload.get("artists")) and payload.get("releasedYearBE") is not None)

    r = session.get(base + f"/static/audio/song_{SAMPLE_SONG_ID}.wav", timeout=20)
    check("ไฟล์เสียงสำรอง .wav เข้าถึงได้", r.status_code == 200 and len(r.content) > 10000,
          f"{r.status_code} / {len(r.content)} bytes")

    r = session.get(base + "/song/99999", timeout=15)
    check("เพลงที่ไม่มีอยู่ ตอบ 404", r.status_code == 404, str(r.status_code))

    # 2) หน้าส่วนตัวต้องถูกกันไว้
    print("\n[2] การป้องกันหน้าส่วนตัว")
    r = session.get(base + "/playlists", allow_redirects=False, timeout=15)
    check("GET /playlists ตอนยังไม่ login -> redirect", r.status_code in (301, 302),
          str(r.status_code))
    check("redirect ไปหน้า login", "/login" in r.headers.get("Location", ""))

    r = session.post(base + "/api/play/1", timeout=15)
    check("POST /api/play ตอนยังไม่ login -> 401", r.status_code == 401, str(r.status_code))

    # 3) เข้าสู่ระบบ
    print("\n[3] เข้าสู่ระบบ")
    r = session.get(base + "/login", timeout=15)
    check("GET /login ตอบ 200", r.status_code == 200, str(r.status_code))

    r = session.post(base + "/login",
                     data={"identity": "demo", "password": "demo1234"},
                     allow_redirects=False, timeout=15)
    check("POST /login (demo/demo1234) สำเร็จ", r.status_code in (301, 302), str(r.status_code))

    r = session.get(base + "/", timeout=15)
    check("หลัง login หน้าแรกแสดงชื่อผู้ใช้", "demo" in r.text)

    # รหัสผ่านผิดต้องถูกปฏิเสธ (ใช้ session ใหม่ เพราะ session ปัจจุบันล็อกอินแล้ว
    # ซึ่งจะถูก redirect ไปหน้าแรกแทนที่จะเห็นฟอร์ม)
    intruder = requests.Session()
    r = intruder.post(base + "/login",
                      data={"identity": "demo", "password": "รหัสผิด"},
                      allow_redirects=True, timeout=15)
    check("รหัสผ่านผิด ถูกปฏิเสธ", "ไม่ถูกต้อง" in r.text)

    # 4) บันทึกการฟัง + PlayCount จาก trigger
    print("\n[4] บันทึกการฟัง (HISTORY + trigger)")
    first = session.post(base + "/api/play/3", timeout=15)
    check("POST /api/play/3 ตอบ 200", first.status_code == 200, str(first.status_code))
    payload = first.json()
    check("response มี ok=true", payload.get("ok") is True, str(payload))
    count_before = payload.get("playCount")

    second = session.post(base + "/api/play/3", timeout=15)
    count_after = second.json().get("playCount")
    check(f"PlayCount เพิ่มขึ้นหลังเล่นซ้ำ ({count_before} -> {count_after})",
          isinstance(count_before, int) and count_after == count_before + 1,
          f"{count_before} -> {count_after}")

    r = session.get(base + "/history", timeout=15)
    check("GET /history ตอบ 200", r.status_code == 200, str(r.status_code))
    check("ประวัติการฟังมีรายการ", "รายการล่าสุด" in r.text)

    # 5) เพลย์ลิสต์ผ่าน stored procedure
    print("\n[5] เพลย์ลิสต์ (stored procedure)")
    name = f"ทดสอบ_{int(time.time())}"
    r = session.post(base + "/playlists/create", data={"plname": name},
                     allow_redirects=False, timeout=15)
    check("สร้างเพลย์ลิสต์ ตอบ redirect", r.status_code in (301, 302), str(r.status_code))
    location = r.headers.get("Location", "")
    check("redirect ไปยังเพลย์ลิสต์ที่สร้าง", "/playlist/" in location, location)
    playlist_id = location.rstrip("/").split("/")[-1] if "/playlist/" in location else None

    r = session.get(base + "/playlists", timeout=15)
    check("เพลย์ลิสต์ใหม่ปรากฏในคลัง", name in r.text)

    if playlist_id:
        r = session.post(base + f"/playlist/{playlist_id}/add",
                         data={"song_id": PLAYLIST_TEST_SONG},
                         allow_redirects=True, timeout=15)
        check("เพิ่มเพลงเข้าเพลย์ลิสต์ได้", r.status_code == 200, str(r.status_code))
        check("เพลย์ลิสต์แสดงเพลงที่เพิ่ม", PLAYLIST_TEST_SONG_TITLE in r.text)

        # เพิ่มซ้ำ -> ต้องไม่ error และไม่สร้างแถวซ้ำ
        r = session.post(base + f"/playlist/{playlist_id}/add",
                         data={"song_id": PLAYLIST_TEST_SONG},
                         allow_redirects=True, timeout=15)
        check("เพิ่มเพลงซ้ำไม่ทำให้ error", r.status_code == 200, str(r.status_code))
        check("แจ้งว่าเพลงมีอยู่แล้ว", "อยู่ในเพลย์ลิสต์แล้ว" in r.text)

        r = session.get(base + f"/playlist/{playlist_id}", timeout=15)
        check("หน้ารายละเอียดเพลย์ลิสต์เปิดได้", r.status_code == 200, str(r.status_code))
        check("แสดงเวลารวมของเพลย์ลิสต์", "เพลง ·" in r.text)

        r = session.post(base + f"/playlist/{playlist_id}/remove",
                         data={"song_id": PLAYLIST_TEST_SONG},
                         allow_redirects=True, timeout=15)
        check("ลบเพลงออกจากเพลย์ลิสต์ได้", "ลบเพลงออกจากเพลย์ลิสต์แล้ว" in r.text)

        r = session.post(base + f"/playlist/{playlist_id}/delete",
                         allow_redirects=True, timeout=15)
        check("ลบเพลย์ลิสต์ได้", r.status_code == 200, str(r.status_code))

    # 6) สิทธิ์การแก้ไขเพลย์ลิสต์ของคนอื่น
    print("\n[6] สิทธิ์การเข้าถึง")
    r = session.post(base + "/playlist/3/add", data={"song_id": 1}, timeout=15)
    check("แก้เพลย์ลิสต์ของคนอื่น -> 403", r.status_code == 403, str(r.status_code))

    r = session.get(base + "/playlist/3", timeout=15)
    check("ดูเพลย์ลิสต์ของคนอื่นได้ (read-only)", r.status_code == 200, str(r.status_code))

    # 7) สมัคร / เข้าสู่ระบบด้วยอีเมล + OTP
    print("\n[7] สมัคร/เข้าสู่ระบบด้วยอีเมล (OTP)")
    new_email = f"smoke{int(time.time())}@example.com"
    fresh = requests.Session()

    r = fresh.post(base + "/register", data={"email": new_email},
                   allow_redirects=False, timeout=20)
    check("อีเมลใหม่ -> ไปหน้าวันเกิด", "/register/details" in r.headers.get("Location", ""),
          r.headers.get("Location", ""))

    r = fresh.post(base + "/register/details",
                   data={"username": f"smoke{int(time.time())}", "password": "testpass123",
                         "day": "15", "month": "6", "year": "1999",
                         "gender": "Male", "country": "TH", "tel": "0800000000",
                         "terms": "on"},
                   allow_redirects=False, timeout=20)
    check("กรอกข้อมูลครบ + ยอมรับข้อกำหนด -> ไปหน้ากรอกรหัส",
          "/auth/code" in r.headers.get("Location", ""), r.headers.get("Location", ""))

    code = read_email_code(new_email)
    check("มีรหัสเก็บในฐานข้อมูล", bool(code), str(code))

    r = fresh.post(base + "/auth/code", data={"code": "000000"}, allow_redirects=True, timeout=20)
    check("รหัสผิดถูกปฏิเสธ", "รหัสไม่ถูกต้อง" in r.text)

    r = fresh.post(base + "/auth/code", data={"code": code}, allow_redirects=False, timeout=20)
    check("รหัสถูก -> เข้าระบบ", r.status_code in (301, 302), str(r.status_code))

    r = fresh.get(base + "/playlists", timeout=15)
    check("บัญชีใหม่ที่สร้างจากอีเมลใช้งานได้", r.status_code == 200, str(r.status_code))

    check("รหสถูกลบหลังใช้ (ใช้ซ้ำไม่ได้)", read_email_code(new_email) is None)

    repeat = requests.Session()
    r = repeat.post(base + "/register", data={"email": new_email},
                    allow_redirects=False, timeout=20)
    check("อีเมลเดิม -> ข้ามไปหน้ากรอกรหัสทันที",
          "/auth/code" in r.headers.get("Location", ""), r.headers.get("Location", ""))

    # 8) เก็บกวาดข้อมูลที่ทดสอบสร้างขึ้น
    print("\n[8] เก็บกวาดข้อมูลทดสอบ")
    try:
        detail = cleanup_test_data()
        check("ลบข้อมูลทดสอบเรียบร้อย", True, detail)
        print(f"      {detail}")
    except Exception as exc:  # noqa: BLE001 - รายงานแล้วไปต่อ
        check("ลบข้อมูลทดสอบเรียบร้อย", False, str(exc))

    # ------------------------------------------------------------------
    print("\n" + "=" * 58)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"ผลรวม: {passed}/{total} ผ่าน")
    if passed != total:
        print("\nรายการที่ไม่ผ่าน:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name} {detail}")
    print("=" * 58)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
