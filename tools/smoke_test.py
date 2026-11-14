"""
smoke_test.py - end-to-end test of the web app over HTTP

The web server must be running first (python run.py), then run
    python tools/smoke_test.py
    python tools/smoke_test.py --base http://127.0.0.1:5000

Checks that: main pages load, search works, login works, a play really bumps
PlayCount, songs can be created/added/removed in playlists through stored
procedures, registration works, and the error page behaves correctly
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

import requests

# so that app.config can be imported no matter which folder we run from
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, bool, str]] = []

# ---- reference data from db/02_seed.sql (edit here only if the seed changes) ----
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


def cleanup_test_data() -> str:
    """Delete playlists/users the smoke test created so the real DB stays clean"""
    import pyodbc

    from app.config import Config

    with pyodbc.connect(Config.CONNECTION_STRING, autocommit=True) as conn:
        cur = conn.cursor()
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

    # 1) private pages need a login first
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

    # the "see all" page you reach from a button on the home page
    r = session.get(base + "/songs", timeout=15)
    check("GET /songs (เพลงทั้งหมด) ตอบ 200", r.status_code == 200, str(r.status_code))
    check("หน้า /songs มีรายการเพลง", r.text.count('class="track"') >= 20,
          str(r.text.count('class="track"')))

    # the "play popular songs" button must find the cards (it broke when the list became cards)
    r = session.get(base + "/", timeout=15)
    check("หน้าแรกมีปุ่มเล่นทั้งรายการ", "data-play-list" in r.text)
    check("การ์ดเพลงมี data-id สำหรับเล่น", r.text.count('class="rail-card"') >= 5
          and 'data-id=' in r.text)

    # settings sub-pages (tabs) - use a dedicated signed-in client so the
    # guest-session tests further down are unaffected
    st = requests.Session()
    st.post(base + "/login", data={"identity": "demo", "password": "demo1234"},
            allow_redirects=True, timeout=20)

    r = st.get(base + "/settings", allow_redirects=False, timeout=15)
    location = r.headers.get("Location", "")
    check("GET /settings redirect ไป /settings/general",
          r.status_code in (301, 302) and location.endswith("/settings/general"),
          f"{r.status_code} {location}")

    for tab in ("general", "account", "about"):
        r = st.get(f"{base}/settings/{tab}", timeout=15)
        check(f"GET /settings/{tab} ตอบ 200", r.status_code == 200, str(r.status_code))

    r = st.get(base + "/settings/account", timeout=15)
    check("หน้า account แสดงอีเมลผู้ใช้", "demo@example.com" in r.text)

    r = st.get(base + "/settings/nope", timeout=15)
    check("แท็บที่ไม่มีอยู่ -> 404", r.status_code == 404, str(r.status_code))

    # ---- search suggestions (type-ahead) ----
    r = session.get(base + "/api/suggest", params={"q": "s"}, timeout=15)
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    check("GET /api/suggest?q=s ตอบ 200 + JSON", r.status_code == 200 and bool(data), str(r.status_code))
    check("suggest คืนทั้งเพลงและศิลปิน",
          bool(data.get("songs")) and bool(data.get("artists")),
          f"songs={len(data.get('songs', []))} artists={len(data.get('artists', []))}")
    check("suggest จำกัดจำนวน (ไม่เกิน 10 รายการ)",
          len(data.get("songs", [])) <= 6 and len(data.get("artists", [])) <= 4)

    r = session.get(base + "/api/suggest", params={"q": ""}, timeout=15)
    empty = r.json()
    check("suggest คำว่าง คืนลิสต์ว่าง", empty.get("songs") == [] and empty.get("artists") == [])

    r = session.get(base + "/api/suggest", params={"q": "zzzzqqq"}, timeout=15)
    none = r.json()
    check("suggest คำที่ไม่มี คืนลิสต์ว่าง ไม่ error",
          r.status_code == 200 and none.get("songs") == [] and none.get("artists") == [])

    r = st.get(base + "/settings/account/change-password", timeout=15)
    check("GET /settings/account/change-password ตอบ 200", r.status_code == 200, str(r.status_code))
    check("หน้ารหัสผ่านมีฟอร์ม", "password-form" in r.text)

    r = st.get(base + "/settings/password", timeout=15)
    check("GET /settings/password -> 404 (ไม่ใช่แท็บ)", r.status_code == 404, str(r.status_code))

    r = st.post(base + "/settings/account/change-password",
                data={"current": "wrong-password", "new": "abcdefgh", "confirm": "abcdefgh"},
                allow_redirects=True, timeout=20)
    check("รหัสผ่านปัจจุบันผิด ถูกปฏิเสธ", "รหัสผ่านปัจจุบันไม่ถูกต้อง" in r.text)

    r = st.post(base + "/settings/account/change-password",
                data={"current": "demo1234", "new": "abcdefgh", "confirm": "zzzzzzzz"},
                allow_redirects=True, timeout=20)
    check("ยืนยันรหัสผ่านไม่ตรง ถูกปฏิเสธ", "ไม่ตรงกัน" in r.text)

    # CSS guard: the player bar must stay fixed (a later "position: relative"
    # rule once knocked it out of the viewport)
    css_dir = pathlib.Path(__file__).resolve().parent.parent / "app" / "static" / "css"
    css = "".join((css_dir / name).read_text(encoding="utf-8")
                   for name in ("base.css", "layout.css", "components.css",
                                "forms.css", "player.css", "pages.css"))
    check("CSS: .player เป็น position: fixed",
          ".player {\n  position: fixed;" in css)
    check("CSS: ไม่มีกฎทับ position ของ .player",
          ".app, .player" not in css)

    r = session.get(base + "/artists", timeout=15)
    check("GET /artists (ศิลปินทั้งหมด) ตอบ 200", r.status_code == 200, str(r.status_code))
    check("หน้า /artists มีการ์ดศิลปิน", r.text.count('class="artist-card"') >= 10,
          str(r.text.count('class="artist-card"')))

    # regression: collab credits must all show (they went missing when we used only the first artistName)
    r = session.get(base + "/song/68", timeout=15)
    check("เพลงคอลแลบแสดงศิลปินครบ (PUN, The Toys)",
          r.status_code == 200 and "PUN" in r.text and "The Toys" in r.text,
          str(r.status_code))
    r = session.get(base + "/song/101", timeout=15)
    check("เพลงที่มี feat. แสดงศิลปินรับเชิญด้วย", "Khalid" in r.text, str(r.status_code))

    # API the full-screen player uses to fetch credits (the "credits" tab, no page change)
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

    # 2) private pages must be blocked
    print("\n[2] การป้องกันหน้าส่วนตัว")
    r = session.get(base + "/playlists", allow_redirects=False, timeout=15)
    check("GET /playlists ตอนยังไม่ login -> redirect", r.status_code in (301, 302),
          str(r.status_code))
    check("redirect ไปหน้า login", "/login" in r.headers.get("Location", ""))

    r = session.post(base + "/api/play/1", timeout=15)
    check("POST /api/play ตอนยังไม่ login -> 401", r.status_code == 401, str(r.status_code))

    # 3) log in
    print("\n[3] เข้าสู่ระบบ")
    r = session.get(base + "/login", timeout=15)
    check("GET /login ตอบ 200", r.status_code == 200, str(r.status_code))

    r = session.post(base + "/login",
                     data={"identity": "demo", "password": "demo1234"},
                     allow_redirects=False, timeout=15)
    check("POST /login (demo/demo1234) สำเร็จ", r.status_code in (301, 302), str(r.status_code))

    r = session.get(base + "/", timeout=15)
    check("หลัง login หน้าแรกแสดงชื่อผู้ใช้", "demo" in r.text)

    # a wrong password must be rejected (use a fresh session, because the current one
    # is logged in and would be redirected home instead of showing the form)
    intruder = requests.Session()
    r = intruder.post(base + "/login",
                      data={"identity": "demo", "password": "รหัสผิด"},
                      allow_redirects=True, timeout=15)
    check("รหัสผ่านผิด ถูกปฏิเสธ", "ไม่ถูกต้อง" in r.text)

    # 4) play logging + PlayCount from the trigger
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

    # 5) playlists via stored procedure
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

        # adding it again -> must not error and must not create a duplicate row
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

    # 6) edit permission on someone else's playlist
    print("\n[6] สิทธิ์การเข้าถึง")
    r = session.post(base + "/playlist/3/add", data={"song_id": 1}, timeout=15)
    check("แก้เพลย์ลิสต์ของคนอื่น -> 403", r.status_code == 403, str(r.status_code))

    r = session.get(base + "/playlist/3", timeout=15)
    check("ดูเพลย์ลิสต์ของคนอื่นได้ (read-only)", r.status_code == 200, str(r.status_code))

    # 7) Sign up (single password form)
    print("\n[7] สมัครสมาชิก")
    new_user = f"smoke{int(time.time())}"
    fresh = requests.Session()

    signup = {
        "username": new_user,
        "password": "testpass123",
        "email": f"{new_user}@example.com",
        "day": "15", "month": "6", "year": "1999",
        "gender": "Male", "country": "TH", "tel": "0800000000",
        "terms": "on",
    }
    r = fresh.post(base + "/register", data=signup, allow_redirects=False, timeout=20)
    check("สมัครสมาชิกสำเร็จ", r.status_code in (301, 302), str(r.status_code))
    check("ล็อกอินอัตโนมัติหลังสมัคร", new_user in fresh.get(base + "/", timeout=15).text)

    dup = requests.Session()
    r = dup.post(base + "/register", data=signup, allow_redirects=True, timeout=20)
    check("สมัครซ้ำด้วยชื่อเดิม ถูกปฏิเสธ", "ถูกใช้แล้ว" in r.text)

    bad = requests.Session()
    weak = dict(signup, username=f"weak{int(time.time())}",
                email=f"weak{int(time.time())}@example.com", password="123")
    r = bad.post(base + "/register", data=weak, allow_redirects=True, timeout=20)
    check("รหัสผ่านสั้นเกินไป ถูกปฏิเสธ", "อย่างน้อย 8 ตัวอักษร" in r.text)

    r = requests.Session().post(base + "/login",
                               data={"identity": new_user, "password": "testpass123"},
                               allow_redirects=False, timeout=20)
    check("ล็อกอินด้วยบัญชีที่เพิ่งสมัครได้", r.status_code in (301, 302), str(r.status_code))

    # 8) clean up the data the test created
    print("\n[8] เก็บกวาดข้อมูลทดสอบ")
    try:
        detail = cleanup_test_data()
        check("ลบข้อมูลทดสอบเรียบร้อย", True, detail)
        print(f"      {detail}")
    except Exception as exc:  # noqa: BLE001 - report it and carry on
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
