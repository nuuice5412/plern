
"""Sign in, sign up, sign out"""
from __future__ import annotations

import datetime as dt
import re

import pyodbc

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
# Sign up / log in / log out
# ---------------------------------------------------------------------------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        identity = (request.form.get("identity") or "").strip()
        password = request.form.get("password") or ""

        row = db.query_one(
            "SELECT UserID, Username, Password FROM dbo.[User] WHERE Username = ? OR Email = ?",
            (identity, identity),
        )
        if row and verify_password(password, row["Password"]):
            session.clear()
            session["user_id"] = row["UserID"]
            flash(f"ยินดีต้อนรับกลับมา {row['Username']} 👋", "success")
            nxt = request.form.get("next") or request.args.get("next")
            # Block open redirects: accept only paths inside this site
            if nxt and nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(url_for("main.index"))

        flash("ชื่อผู้ใช้/อีเมล หรือรหัสผ่านไม่ถูกต้อง", "error")

    return render_template("login.html", next=request.args.get("next", ""))


# ---------------------------------------------------------------------------
# Sign up (single password-based form)
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@bp.route("/register", methods=["GET", "POST"])
def register():
    """One form that fills every column of the USER table and creates the account"""
    if g.user:
        return redirect(url_for("main.index"))

    days = range(1, 32)
    months = [(1, "ม.ค."), (2, "ก.พ."), (3, "มี.ค."), (4, "เม.ย."), (5, "พ.ค."), (6, "มิ.ย."),
              (7, "ก.ค."), (8, "ส.ค."), (9, "ก.ย."), (10, "ต.ค."), (11, "พ.ย."), (12, "ธ.ค.")]
    this_year = dt.date.today().year
    years = range(this_year - 13, this_year - 90, -1)
    countries = [("TH", "ไทย"), ("US", "สหรัฐอเมริกา"), ("GB", "อังกฤษ"),
                 ("JP", "ญี่ปุ่น"), ("KR", "เกาหลีใต้"), ("CN", "จีน"),
                 ("VN", "เวียดนาม"), ("LA", "ลาว"), ("MM", "เมียนมา"),
                 ("SG", "สิงคโปร์"), ("MY", "มาเลเซีย"), ("ID", "อินโดนีเซีย")]
    genders = [("Male", "ชาย"), ("Female", "หญิง"), ("", "ไม่ระบุ")]

    def render(form=None, error=None):
        if error:
            flash(error, "error")
        return render_template("register.html", days=days, months=months, years=years,
                               countries=countries, genders=genders, form=form or {})

    if request.method == "POST":
        f = request.form
        username = (f.get("username") or "").strip()
        email = (f.get("email") or "").strip().lower()
        password = f.get("password") or ""
        gender = (f.get("gender") or "").strip()
        country = (f.get("country") or "").strip()
        tel = (f.get("tel") or "").strip()

        if not re.fullmatch(r"[A-Za-z0-9._-]{3,50}", username):
            return render(f, "ชื่อผู้ใช้ต้องยาว 3–50 ตัว ใช้ได้เฉพาะ a-z 0-9 . _ -")
        if len(password) < 8:
            return render(f, "รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร")
        if not EMAIL_RE.match(email):
            return render(f, "อีเมลไม่ถูกต้องครับ")
        if db.query_one("SELECT 1 AS x FROM dbo.[User] WHERE Username = ?", (username,)):
            return render(f, "ชื่อผู้ใช้นี้ถูกใช้แล้ว กรุณาเลือกชื่ออื่น")
        if db.query_one("SELECT 1 AS x FROM dbo.[User] WHERE Email = ?", (email,)):
            return render(f, "อีเมลนี้ถูกใช้แล้ว กรุณาใช้อีเมลอื่น")

        try:
            dob = dt.date(int(f.get("year")), int(f.get("month")), int(f.get("day")))
        except (ValueError, TypeError):
            return render(f, "กรุณาเลือกวันเกิดให้ครบ")
        if (dt.date.today() - dob).days // 365 < 13:
            return render(f, "ต้องมีอายุ 13 ปีขึ้นไปจึงจะสมัครได้")

        if not f.get("terms"):
            return render(f, "กรุณายอมรับข้อกำหนดการใช้งานก่อน")
        if tel and not re.fullmatch(r"[0-9+ -]{9,20}", tel):
            return render(f, "เบอร์โทรไม่ถูกต้อง")

        try:
            rows = db.call_proc(
                """
                DECLARE @new_id INT;
                EXEC dbo.usp_User_Register
                     @Username = ?, @Password = ?, @Email = ?, @Gender = ?,
                     @Date_of_Birth = ?, @Country = ?, @Tel = ?,
                     @NewUserID = @new_id OUTPUT;
                SELECT @new_id AS NewUserID;
                """,
                (
                    username,
                    hash_password(password),
                    email,
                    gender if gender in ("Male", "Female") else None,
                    dob.isoformat(),
                    country if country in {c for c, _ in countries} else None,
                    tel or None,
                ),
            )
        except pyodbc.Error as exc:
            return render(f, db.db_message(exc))

        if rows and rows[0]["NewUserID"]:
            session.clear()
            session["user_id"] = rows[0]["NewUserID"]
            flash(f"สมัครสมาชิกสำเร็จ ยินดีต้อนรับ {username} 👋", "success")
            return redirect(url_for("main.index"))

        return render(f, "สมัครสมาชิกไม่สำเร็จ กรุณาลองใหม่")

    return render()


@bp.get("/logout")
def logout():
    session.clear()
    flash("ออกจากระบบแล้ว", "success")
    return redirect(url_for("main.index"))


