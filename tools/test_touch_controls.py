"""ทดสอบบนมือถือ: ปุ่มเล่นบนการ์ด/ตารางต้องมองเห็นและกดได้ (ไม่มี hover)"""
import json
import subprocess
import time
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9680

proc = subprocess.Popen(
    [CHROME, "--headless=new", "--disable-gpu", "--mute-audio",
     "--autoplay-policy=no-user-gesture-required", "--hide-scrollbars",
     f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
     r"--user-data-dir=C:\Users\IMOS\AppData\Local\Temp\cdp-touch",
     "--window-size=390,844", "--no-first-run", "http://127.0.0.1:5000/"],
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


call("Runtime.enable")
call("Emulation.setDeviceMetricsOverride",
     {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True})
call("Emulation.setTouchEmulationEnabled", {"enabled": True})
call("Emulation.setEmulatedMedia", {"features": [{"name": "hover", "value": "none"},
                                                {"name": "pointer", "value": "coarse"}]})
time.sleep(3)

print("hover: none ใช้ได้:", ev("matchMedia('(hover: none)').matches"))
print("ปุ่มเล่นการ์ด (เพลงออกใหม่) opacity:",
      ev("getComputedStyle(document.querySelector('#rail-new .rail-play')).opacity"))
print("ขนาดปุ่ม:", ev(
    "JSON.stringify((function(){var r=document.querySelector('#rail-new .rail-play')"
    ".getBoundingClientRect();return [Math.round(r.width),Math.round(r.height)];})())"))

print("\n--- แตะปุ่มเล่นที่การ์ด 'เพลงออกใหม่' ---")
ev("document.querySelector('#rail-new .rail-play').click(); 'ok'")
time.sleep(2)
print(ev("JSON.stringify({title: document.getElementById('np-title').textContent,"
       " playing: !document.getElementById('audio').paused,"
       " url: location.pathname})"))

print("\n--- ไปหน้าตาราง /songs แล้วดูปุ่มเล่น ---")
ev("location.href='/songs'; 'ok'")
time.sleep(2.5)
print("ปุ่ม .play-toggle ที่มองเห็นได้:",
      ev("Array.from(document.querySelectorAll('tr.track .play-toggle'))"
         ".filter(function(b){return getComputedStyle(b).display !== 'none';}).length"))
ev("document.querySelector('tr.track .play-toggle').click(); 'ok'")
time.sleep(1.8)
print("เล่นจากตาราง:", ev("document.getElementById('np-title').textContent"))

print("\njs errors:", errors or "ไม่มี")
ws.close()
proc.terminate()
