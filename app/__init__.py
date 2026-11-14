"""Flask application factory"""
from __future__ import annotations

import datetime as dt
import mimetypes

from flask import Flask, g, session

from . import db
from . import artwork
from .config import Config

# The Windows registry may not recognize .m4a, so Flask sends Content-Type audio/m4a
# which is not a standard MIME type; some browsers refuse to play it -> force audio/mp4
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("application/manifest+json", ".webmanifest")
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
    # Load the current user from the session once per request
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
            if g.user is None:      # user has been deleted
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
        """4980 -> '1 ชม. 23 น.' (Thai) or '1 h 23 m' (English)"""
        total = int(seconds or 0)
        hours, minutes = divmod(total // 60, 60)
        from .i18n import current_language

        if current_language() == "en":
            return f"{hours} h {minutes} m" if hours else f"{minutes} m"
        return f"{hours} ชม. {minutes} น." if hours else f"{minutes} น."

    @app.template_filter("thaidate")
    def thaidate(value: dt.date | dt.datetime | None, with_time: bool = True) -> str:
        """2025-01-15 -> '15 Jan 2568' (Buddhist Era, + 543)"""
        if value is None:
            return "-"
        buddhist_year = value.year + 543
        text = f"{value.day} {THAI_MONTHS[value.month - 1]} {buddhist_year}"
        if with_time and isinstance(value, dt.datetime):
            text += f" {value:%H:%M}"
        return text

    @app.template_filter("hue")
    def hue(song_id: int | None) -> int:
        """Generate a deterministic cover color from SongID (used as a CSS variable)"""
        return ((int(song_id or 1) * 47) % 360)

    @app.context_processor
    def inject_i18n() -> dict:
        from .i18n import current_language, translate

        return {"t": translate, "lang": current_language()}

    @app.template_filter("mask_email")
    def mask_email(value: str | None) -> str:
        """rookstargame1234@gmail.com -> r***4@g****l.com (as Tidal displays it)"""
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

    # Cover/artist images (read from static/img/manifest.json)
    app.jinja_env.globals["cover_url"] = artwork.cover_url
    app.jinja_env.globals["artist_photo_url"] = artwork.artist_photo_url

    return app
