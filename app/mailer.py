"""
mailer.py - send OTP codes by email

Supports 2 modes
  1) Real SMTP  : set 4 environment variables
        set SMTP_HOST=smtp.gmail.com
        set SMTP_PORT=587
        set SMTP_USER=you@gmail.com
        set SMTP_PASS=<16-character Gmail App Password>
     (Gmail requires 2-Step Verification enabled, then create an App Password)
  2) Test mode : if not configured, print the code to the console + return "console"
     so demos work without a real email account
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
    """Send the code and return the channel actually used: 'smtp' or 'console'"""
    if not is_configured():
        print(f"[MAIL-DEV] รหัสสำหรับ {to_email} = {code}")
        return "console"

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    sender = os.environ.get("SMTP_FROM") or os.environ["SMTP_USER"]

    message = EmailMessage()
    message["Subject"] = f"Plern — รหัสเข้าสู่ระบบของคุณคือ {code}"
    message["From"] = sender
    message["To"] = to_email
    message.set_content(
        f"รหัสเข้าสู่ระบบ Plern ของคุณคือ {code}\n"
        "รหัสนี้ใช้ได้ 10 นาที\n\n"
        "หากคุณไม่ได้เป็นผู้ขอรหัสนี้ ไม่ต้องทำอะไรครับ"
    )

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls(context=context)
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        server.send_message(message)
    return "smtp"
