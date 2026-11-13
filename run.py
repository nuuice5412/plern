"""
run.py - จุดเริ่มต้นของเว็บแอป

    python run.py                        # http://127.0.0.1:5000 (เครื่องตัวเองเท่านั้น)
    set HOST=0.0.0.0 && python run.py     # ให้เครื่องอื่นในวง LAN เข้าถึงได้
    set PORT=8000 && python run.py       # เปลี่ยนพอร์ต
    set FLASK_DEBUG=0 && python run.py   # ปิด debug (ใช้ตอนให้คนอื่นทดสอบ)
"""
from __future__ import annotations

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") not in ("0", "false", "no")

    if host != "127.0.0.1":
        print(f"\n  เปิดให้เครื่องอื่นเข้าถึงได้ที่  http://<IP ของเครื่องนี้>:{port}")
        print("  (ถ้าเข้าจากเครื่องอื่นไม่ได้ ให้เปิด Windows Firewall สำหรับพอร์ตนี้)\n")

    app.run(host=host, port=port, debug=debug)
