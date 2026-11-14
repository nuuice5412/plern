
"""HTTP error handlers"""
from __future__ import annotations

import datetime as dt
import re

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from . import bp
from .common import (
    EMAIL_RE,
    _int_arg,
    _owned_playlist_or_404,
    _playlists_of,
)
from .. import db
from ..auth import hash_password, login_required, verify_password

# ---------------------------------------------------------------------------
# error handler
# ---------------------------------------------------------------------------
@bp.app_errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403,
                           message="คุณไม่มีสิทธิ์แก้ไขเพลย์ลิสต์นี้"), 403


@bp.app_errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404,
                           message="ไม่พบหน้าที่คุณเปิด หรือข้อมูลถูกลบไปแล้ว"), 404




