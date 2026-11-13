"""ทดสอบปุ่มก่อนหน้า/ถัดไป/สุ่ม/เล่นซ้ำ บนหน้าแรก (การ์ด 20 เพลง)"""
import json
import subprocess
import time
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9660

proc = subprocess.Popen(
    [CHROME, "--headless=new", "--disable-gpu", "--mute-audio",
     "--autoplay-policy=no-user-gesture-required",
     f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
     r"--user-data-dir=C:\Users\IMOS\AppData\Local\Temp\cdp-controls",
     "--window-size=1440,900", "--no-first-run", "http://127.0.0.1:5000/"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

ws_url = None
for _ in range(40):
    time.sleep(0.5)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=2) as res:
            pages = [t for t in json.load(res) if t.get("type") == "page"]
        if pages:
            ws_url = pages[0]["webSocketDebuggerUrl"]
            break
    except Exception:
        pass

ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
counter = {"id": 0}
errors = []


def call(method, params=None):
    counter["id"] += 1
    mid = counter["id"]
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("method") == "Runtime.exceptionThrown":
            errors.append(msg["params"]["exceptionDetails"].get("text"))
        if msg.get("id") == mid:
            return msg


def ev(expr):
    res = call("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
    return res["result"]["result"].get("value")


def title():
    return ev("document.getElementById('np-title').textContent")


call("Runtime.enable")
time.sleep(3)

print("=== 1) กดเล่นการ์ดที่ 2 ===")
ev("document.querySelectorAll('#rail-top .rail-play')[1].click(); 'ok'")
time.sleep(1.5)
print("   กำลังเล่น:", title())

print("\n=== 2) ปุ่มถัดไป ===")
ev("document.getElementById('btn-next').click(); 'ok'")
time.sleep(1.3)
after_next = title()
print("   หลังกด next:", after_next, "| เปลี่ยน:", after_next != "♥")

print("\n=== 3) ปุ่มก่อนหน้า ===")
ev("document.getElementById('btn-prev').click(); 'ok'")
time.sleep(1.3)
print("   หลังกด prev:", title())

print("\n=== 4) สุ่มเพลง ===")
ev("document.getElementById('btn-shuffle').click(); 'ok'")
time.sleep(0.4)
print("   สถานะ shuffle:", ev("document.getElementById('btn-shuffle').classList.contains('is-active')"))
before = title()
ev("document.getElementById('btn-next').click(); 'ok'")
time.sleep(1.4)
print(f"   กด next ตอนสุ่ม: {before!r} -> {title()!r}")
ev("document.getElementById('btn-shuffle').click(); 'ok'")   # ปิดกลับ

print("\n=== 5) เล่นซ้ำแบบ 'เพลงเดียว' ===")
ev("document.getElementById('btn-repeat').click(); 'ok'")     # all
ev("document.getElementById('btn-repeat').click(); 'ok'")     # one
time.sleep(0.3)
print("   repeat mode:", ev("document.getElementById('btn-repeat').dataset.mode"))
t_before = title()
ev("document.getElementById('audio').dispatchEvent(new Event('ended')); 'ok'")
time.sleep(1.2)
print(f"   หลังเพลงจบ: {t_before!r} -> {title()!r} (ต้องเป็นเพลงเดิม)")

print("\n=== 6) เล่นซ้ำแบบ 'ทั้งหมด' ที่เพลงสุดท้าย ===")
ev("document.getElementById('btn-repeat').click(); 'ok'")     # -> off
ev("document.getElementById('btn-repeat').click(); 'ok'")     # -> all
time.sleep(0.3)
print("   repeat mode:", ev("document.getElementById('btn-repeat').dataset.mode"))
ev("document.getElementById('audio').dispatchEvent(new Event('ended')); 'ok'")
time.sleep(1.2)
print("   หลังเพลงจบ (ต้องไปเพลงถัดไป):", title())

print("\njs errors:", errors or "ไม่มี")
ws.close()
proc.terminate()
