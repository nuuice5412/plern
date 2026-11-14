
"""Settings tabs, account edit, password, help, terms, service worker"""
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
# Profile menu pages: account settings, help, legal
# ---------------------------------------------------------------------------
SETTINGS_TABS = ("general", "account", "password", "about")


def _settings_tabs(active: str) -> list[dict]:
    """Tab bar entries: (slug, url, i18n key)"""
    return [
        {"slug": "general", "url": url_for("main.settings_tab", tab="general"),
         "label": "settings.tab.general"},
        {"slug": "account", "url": url_for("main.settings_tab", tab="account"),
         "label": "settings.tab.account"},
        {"slug": "about", "url": url_for("main.settings_tab", tab="about"),
         "label": "settings.tab.about"},
    ], active


def _settings_context(tab: str) -> dict:
    user = db.query_one(
        "SELECT UserID, Username, Email, Gender, Date_of_Birth, Country, Tel "
        "FROM dbo.[User] WHERE UserID = ?",
        (g.user["UserID"],),
    )
    if user is None:
        abort(404)

    stats = db.query_one(
        """
        SELECT
          (SELECT COUNT(*) FROM dbo.Playlist WHERE UserID = ?) AS Playlists,
          (SELECT COUNT(*) FROM dbo.Playlist_Detail pd
             JOIN dbo.Playlist p ON p.PlaylistID = pd.PlaylistID
            WHERE p.UserID = ?) AS Tracks,
          (SELECT COUNT(*) FROM dbo.History WHERE UserID = ?) AS Plays,
          (SELECT ISNULL(SUM(s.Duration), 0) FROM dbo.History h
             JOIN dbo.Song s ON s.SongID = h.SongID
            WHERE h.UserID = ?) AS Seconds
        """,
        (g.user["UserID"],) * 4,
    )
    entries, _ = _settings_tabs(tab)
    return {"user": user, "stats": stats, "tab": tab, "tabs": entries}


@bp.get("/settings")
@login_required
def settings():
    """Settings has its own sub-pages; the bare URL opens General"""
    return redirect(url_for("main.settings_tab", tab="general"))


@bp.get("/settings/<tab>")
@login_required
def settings_tab(tab: str):
    if tab not in ("general", "account", "about"):
        abort(404)
    return render_template(f"settings_{tab}.html", **_settings_context(tab))


@bp.route("/settings/account/edit", methods=["GET", "POST"])
@login_required
def account_edit():
    """Separate page for editing the USER row (username, email, profile fields)"""
    user = db.query_one(
        "SELECT UserID, Username, Email, Gender, Date_of_Birth, Country, Tel "
        "FROM dbo.[User] WHERE UserID = ?",
        (g.user["UserID"],),
    )
    if user is None:
        abort(404)

    countries = [("TH", "ไทย"), ("US", "สหรัฐอเมริกา"), ("GB", "อังกฤษ"),
                 ("JP", "ญี่ปุ่น"), ("KR", "เกาหลีใต้"), ("CN", "จีน"),
                 ("VN", "เวียดนาม"), ("LA", "ลาว"), ("MM", "เมียนมา"),
                 ("SG", "สิงคโปร์"), ("MY", "มาเลเซีย"), ("ID", "อินโดนีเซีย")]
    genders = [("Male", "ชาย"), ("Female", "หญิง"), ("", "ไม่ระบุ")]

    days = range(1, 32)
    months = [(1, "ม.ค."), (2, "ก.พ."), (3, "มี.ค."), (4, "เม.ย."), (5, "พ.ค."), (6, "มิ.ย."),
              (7, "ก.ค."), (8, "ส.ค."), (9, "ก.ย."), (10, "ต.ค."), (11, "พ.ย."), (12, "ธ.ค.")]
    this_year = dt.date.today().year
    years = range(this_year - 13, this_year - 90, -1)

    def render(form=None, error=None):
        if error:
            flash(error, "error")
        return render_template("settings_edit.html", form=form or {},
                               countries=countries, genders=genders,
                               days=days, months=months, years=years,
                               **_settings_context("account"))

    if request.method == "POST":
        f = request.form
        username = (f.get("username") or "").strip()
        email = (f.get("email") or "").strip().lower()
        gender = (f.get("gender") or "").strip()
        country = (f.get("country") or "").strip()
        tel = (f.get("tel") or "").strip()
        dob_day = (f.get("day") or "").strip()
        dob_month = (f.get("month") or "").strip()
        dob_year = (f.get("year") or "").strip()

        if not re.fullmatch(r"[A-Za-z0-9._-]{3,50}", username):
            return render(f, "ชื่อผู้ใช้ต้องยาว 3–50 ตัว ใช้ได้เฉพาะ a-z 0-9 . _ -")
        if db.query_one("SELECT 1 AS x FROM dbo.[User] WHERE Username = ? AND UserID <> ?",
                        (username, user["UserID"])):
            return render(f, "ชื่อผู้ใช้นี้ถูกใช้แล้ว")
        if not EMAIL_RE.match(email):
            return render(f, "อีเมลไม่ถูกต้องครับ")
        if db.query_one("SELECT 1 AS x FROM dbo.[User] WHERE Email = ? AND UserID <> ?",
                        (email, user["UserID"])):
            return render(f, "อีเมลนี้ถูกใช้แล้ว")
        if tel and not re.fullmatch(r"[0-9+ -]{9,20}", tel):
            return render(f, "เบอร์โทรไม่ถูกต้อง")

        dob = None
        if dob_day or dob_month or dob_year:
            try:
                dob = dt.date(int(dob_year), int(dob_month), int(dob_day))
            except (ValueError, TypeError):
                return render(f, "กรุณาเลือกวันเกิดให้ครบ")
            if (dt.date.today() - dob).days // 365 < 13:
                return render(f, "ต้องมีอายุ 13 ปีขึ้นไป")

        params = [
            username,
            email,
            gender if gender in ("Male", "Female") else None,
            dob.isoformat() if dob else None,
            country if country in {c for c, _ in countries} else None,
            tel or None,
        ]
        sql = ("UPDATE dbo.[User] SET Username = ?, Email = ?, Gender = ?, "
               "Date_of_Birth = ?, Country = ?, Tel = ? WHERE UserID = ?")
        params.append(user["UserID"])

        db.execute(sql, tuple(params))
        flash("บันทึกข้อมูลบัญชีแล้ว / Account updated", "success")
        return redirect(url_for("main.settings_tab", tab="account"))

    form = {
        "username": user["Username"],
        "email": user["Email"],
        "gender": user["Gender"] or "",
        "day": str(user["Date_of_Birth"].day) if user["Date_of_Birth"] else "",
        "month": str(user["Date_of_Birth"].month) if user["Date_of_Birth"] else "",
        "year": str(user["Date_of_Birth"].year) if user["Date_of_Birth"] else "",
        "country": user["Country"] or "TH",
        "tel": user["Tel"] or "",
    }
    return render(form)


@bp.route("/settings/account/change-password", methods=["GET", "POST"])
@login_required
def change_password_page():
    """Its own page (and tab) for changing the password"""
    if request.method == "POST":
        row = db.query_one("SELECT Password FROM dbo.[User] WHERE UserID = ?",
                           (g.user["UserID"],))
        current = request.form.get("current") or ""
        new = request.form.get("new") or ""
        confirm = request.form.get("confirm") or ""

        if row is None:
            abort(404)
        if not verify_password(current, row["Password"]):
            flash("รหัสผ่านปัจจุบันไม่ถูกต้อง", "error")
        elif len(new) < 8:
            flash("รหัสผ่านใหม่ต้องยาวอย่างน้อย 8 ตัวอักษร", "error")
        elif new != confirm:
            flash("รหัสผ่านใหม่ทั้งสองช่องไม่ตรงกัน", "error")
        else:
            db.execute("UPDATE dbo.[User] SET Password = ? WHERE UserID = ?",
                       (hash_password(new), g.user["UserID"]))
            flash("เปลี่ยนรหัสผ่านแล้ว", "success")
            return redirect(url_for("main.settings_tab", tab="account"))

    entries, _ = _settings_tabs("account")
    return render_template("settings_password.html", tab="account", tabs=entries,
                           user=g.user, stats=None)


@bp.post("/settings/language")
@login_required
def set_language():
    """Persist the UI language and bounce straight back (no save button)"""
    lang = (request.form.get("lang") or "th").lower()
    if lang not in ("th", "en"):
        lang = "th"
    session["lang"] = lang

    target = request.form.get("next") or ""
    if not (target.startswith("/settings") and not target.startswith("//")):
        target = url_for("main.settings_tab", tab="general")
    return redirect(target)


@bp.get("/help")
def help_page():
    return render_template("help.html")


@bp.get("/terms")
def terms():
    return render_template("terms.html")


@bp.get("/sw.js")
def service_worker():
    """Serve the service worker from the root so it can control the whole site"""
    response = send_from_directory(
        current_app.static_folder, "sw.js", mimetype="application/javascript"
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


