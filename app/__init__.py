"""Application factory ของ Flask"""
from __future__ import annotations

import datetime as dt
import mimetypes

from flask import Flask, g, session

from . import db
from . import artwork
from .config import Config

# Windows registry อาจไม่รู้จัก .m4a ทำให้ Flask ส่ง Content-Type เป็น audio/m4a
# ซึ่งไม่ใช่ MIME มาตรฐาน เบราว์เซอร์บางตัวจึงไม่ยอมเล่น -> บังคับเป็น audio/mp4
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")

THAI_MONTHS = [
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)

    from .routes import bp

    app.register_blueprint(bp)

    # ------------------------------------------------------------------
    # โหลดผู้ใช้ปัจจุบันจาก session ครั้งเดียวต่อ request
    # ------------------------------------------------------------------
    @app.before_request
    def load_current_user() -> None:
        g.user = None
        user_id = session.get("user_id")
        if user_id:
            g.user = db.query_one(
                "SELECT UserID, Username, Email, Country FROM dbo.[User] WHERE UserID = ?",
                (user_id,),
            )
            if g.user is None:      # user ถูกลบไปแล้ว
                session.clear()

    # ------------------------------------------------------------------
    # template filters / globals
    # ------------------------------------------------------------------
    @app.template_filter("mmss")
    def mmss(seconds: int | None) -> str:
        """198 -> '3:18'"""
        total = int(seconds or 0)
        return f"{total // 60}:{total % 60:02d}"

    @app.template_filter("hms")
    def hms(seconds: int | None) -> str:
        """4980 -> '1 ชม. 23 น.'"""
        total = int(seconds or 0)
        hours, minutes = divmod(total // 60, 60)
        if hours:
            return f"{hours} ชม. {minutes} น."
        return f"{minutes} น."

    @app.template_filter("thaidate")
    def thaidate(value: dt.date | dt.datetime | None, with_time: bool = True) -> str:
        """2025-01-15 -> '15 ม.ค. 2568' (พ.ศ. + 543)"""
        if value is None:
            return "-"
        buddhist_year = value.year + 543
        text = f"{value.day} {THAI_MONTHS[value.month - 1]} {buddhist_year}"
        if with_time and isinstance(value, dt.datetime):
            text += f" {value:%H:%M}"
        return text

    @app.template_filter("hue")
    def hue(song_id: int | None) -> int:
        """สร้างสีปกเพลงแบบ deterministic จาก SongID (ใช้เป็น CSS variable)"""
        return ((int(song_id or 1) * 47) % 360)

    @app.template_filter("mask_email")
    def mask_email(value: str | None) -> str:
        """rookstargame1234@gmail.com -> r***4@g****l.com (แบบที่ Tidal แสดง)"""
        if not value or "@" not in value:
            return value or ""
        local, domain = value.split("@", 1)
        name, _, tld = domain.rpartition(".")

        masked_local = local[:1] + "***" + (local[-1:] if len(local) > 2 else "")
        if name:
            tail = name[-1:] if len(name) > 2 else ""
            masked_domain = f"{name[:1]}****{tail}.{tld}"
        else:
            masked_domain = domain
        return f"{masked_local}@{masked_domain}"

    @app.context_processor
    def inject_globals() -> dict:
        return {
            "current_user": g.get("user"),
            "app_name": app.config["APP_NAME"],
        }

    # รูปปก/รูปศิลปิน (อ่านจาก static/img/manifest.json)
    app.jinja_env.globals["cover_url"] = artwork.cover_url
    app.jinja_env.globals["artist_photo_url"] = artwork.artist_photo_url

    return app
