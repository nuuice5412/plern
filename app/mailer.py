"""
mailer.py - ส่งรหัส OTP ทางอีเมล

รองรับ 2 โหมด
  1) SMTP จริง  : ตั้ง environment variable 4 ตัว
        set SMTP_HOST=smtp.gmail.com
        set SMTP_PORT=587
        set SMTP_USER=you@gmail.com
        set SMTP_PASS=<App Password 16 ตัวของ Gmail>
     (Gmail ต้องเปิด 2-Step Verification แล้วสร้าง App Password)
  2) โหมดทดสอบ : ถ้าไม่ได้ตั้งค่า จะพิมพ์รหัสลงคอนโซล + คืนค่า "console"
     เพื่อให้เดโมได้โดยไม่ต้องมีอีเมลจริง
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

REQUIRED = ("SMTP_HOST", "SMTP_USER", "SMTP_PASS")


def is_configured() -> bool:
    return all(os.environ.get(key) for key in REQUIRED)


def send_code(to_email: str, code: str) -> str:
    """ส่งรหัส แล้วคืนค่าช่องทางที่ใช้จริง: 'smtp' หรือ 'console'"""
    if not is_configured():
        print(f"[MAIL-DEV] รหัสสำหรับ {to_email} = {code}")
        return "console"

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    sender = os.environ.get("SMTP_FROM") or os.environ["SMTP_USER"]

    message = EmailMessage()
    message["Subject"] = f"Spi Music — รหัสเข้าสู่ระบบของคุณคือ {code}"
    message["From"] = sender
    message["To"] = to_email
    message.set_content(
        f"รหัสเข้าสู่ระบบ Spi Music ของคุณคือ {code}\n"
        "รหัสนี้ใช้ได้ 10 นาที\n\n"
        "หากคุณไม่ได้เป็นผู้ขอรหัสนี้ ไม่ต้องทำอะไรครับ"
    )

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls(context=context)
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        server.send_message(message)
    return "smtp"
