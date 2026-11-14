"""
All web app routes live here.

Query design notes:
 - Read data through VIEWs (vw_SongDetail / vw_PlaylistSummary / vw_PlaylistTrackList)
   to avoid rewriting JOINs in many places and to match the derived attribute idea in the ER
 - Write data (register, create playlist, add/remove song, record a play)
   through STORED PROCEDUREs so business rules live in one place in the database
 - Every user value is passed as a parameter (?) — never concatenated into SQL
"""
from __future__ import annotations

import datetime as dt
import re

import pyodbc
from flask import (
    Blueprint,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from . import db
from .auth import hash_password, login_required, verify_password

bp = Blueprint("main", __name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _int_arg(name: str) -> int | None:
    raw = request.form.get(name) or request.args.get(name)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _playlists_of(user_id: int) -> list[dict]:
    return db.query(
        "SELECT * FROM dbo.vw_PlaylistSummary WHERE UserID = ? ORDER BY Create_Date DESC",
        (user_id,),
    )


def _owned_playlist_or_404(playlist_id: int) -> dict:
    row = db.query_one(
        "SELECT PlaylistID, PLname, UserID FROM dbo.Playlist WHERE PlaylistID = ?",
        (playlist_id,),
    )
    if row is None:
        abort(404)
    if g.user is None or row["UserID"] != g.user["UserID"]:
        abort(403)
    return row


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------
@bp.get("/")
def index():
    top_songs = db.query("SELECT TOP (20) * FROM dbo.vw_TopSongs")

    artists = db.query(
        """
        SELECT TOP (20) a.ArtistID, a.ArtistName, a.Country, x.SongCount, x.TotalPlays
        FROM dbo.Artist AS a
        OUTER APPLY (
            SELECT COUNT(*) AS SongCount, ISNULL(SUM(s.PlayCount), 0) AS TotalPlays
            FROM (SELECT DISTINCT SongID FROM dbo.Song_Artist_Role WHERE ArtistID = a.ArtistID) AS d
            JOIN dbo.Song AS s ON s.SongID = d.SongID
        ) AS x
        ORDER BY x.TotalPlays DESC, a.ArtistName
        """
    )

    new_releases = db.query(
        """
        SELECT TOP (12) *
        FROM dbo.vw_SongDetail
        WHERE Released_Date IS NOT NULL
        ORDER BY Released_Date DESC, SongID DESC
        """
    )

    stats = db.query_one(
        """
        SELECT (SELECT COUNT(*) FROM dbo.Song)     AS Songs,
               (SELECT COUNT(*) FROM dbo.Artist)   AS Artists,
               (SELECT COUNT(*) FROM dbo.History)  AS Plays,
               (SELECT COUNT(*) FROM dbo.Playlist) AS Playlists
        """
    )

    recent, my_playlists = [], []
    if g.user:
        recent = db.query(
            """
            SELECT TOP (10) h.Played_At, vd.SongID, vd.SongTitle,
                           vd.MainArtistName, vd.Duration
            FROM dbo.History AS h
            JOIN dbo.vw_SongDetail AS vd ON vd.SongID = h.SongID
            WHERE h.UserID = ?
            ORDER BY h.Played_At DESC
            """,
            (g.user["UserID"],),
        )
        my_playlists = _playlists_of(g.user["UserID"])[:4]

    return render_template(
        "index.html",
        top_songs=top_songs,
        artists=artists,
        new_releases=new_releases,
        stats=stats,
        recent=recent,
        my_playlists=my_playlists,
    )


# ---------------------------------------------------------------------------
# "View all" page (Tidal-style View all)
# ---------------------------------------------------------------------------
ARTIST_LIST_SQL = """
    SELECT a.ArtistID, a.ArtistName, a.Country, x.SongCount, x.TotalPlays
    FROM dbo.Artist AS a
    OUTER APPLY (
        SELECT COUNT(*) AS SongCount, ISNULL(SUM(s.PlayCount), 0) AS TotalPlays
        FROM (SELECT DISTINCT SongID FROM dbo.Song_Artist_Role WHERE ArtistID = a.ArtistID) AS d
        JOIN dbo.Song AS s ON s.SongID = d.SongID
    ) AS x
    ORDER BY x.TotalPlays DESC, a.ArtistName
"""


@bp.get("/songs")
def all_songs():
    """All songs — ?sort=new orders by release date"""
    if (request.args.get("sort") or "top").lower() == "new":
        songs = db.query(
            """
            SELECT TOP (300) * FROM dbo.vw_SongDetail
            WHERE Released_Date IS NOT NULL
            ORDER BY Released_Date DESC, SongID DESC
            """
        )
        heading = "เพลงออกใหม่"
        subtitle = "เรียงตามวันที่วางจำหน่าย — ทั้งหมด %d เพลง" % len(songs)
    else:
        songs = db.query(
            "SELECT TOP (300) * FROM dbo.vw_SongDetail ORDER BY PlayCount DESC, SongTitle"
        )
        heading = "เพลงทั้งหมด"
        subtitle = "เรียงตามจำนวนครั้งที่ถูกเล่น — ทั้งหมด %d เพลง" % len(songs)

    return render_template("songs.html", songs=songs, heading=heading, subtitle=subtitle)


@bp.get("/artists")
def all_artists():
    artists = db.query(ARTIST_LIST_SQL)
    return render_template(
        "artists.html",
        artists=artists,
        subtitle="ศิลปินทั้งหมด %d คน — เรียงตามยอดฟัง" % len(artists),
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
@bp.get("/search")
def search():
    q = (request.args.get("q") or "").strip()
    songs, artists = [], []
    if q:
        like = f"%{q}%"
        songs = db.query(
            """
            SELECT TOP (50) *
            FROM dbo.vw_SongDetail
            WHERE SongTitle LIKE ? OR MainArtistName LIKE ? OR ArtistRoleList LIKE ?
            ORDER BY PlayCount DESC, SongTitle
            """,
            (like, like, like),
        )
        artists = db.query(
            """
            SELECT TOP (20) ArtistID, ArtistName, Country, Bio
            FROM dbo.Artist
            WHERE ArtistName LIKE ? OR Bio LIKE ?
            ORDER BY ArtistName
            """,
            (like, like),
        )
    return render_template("search.html", q=q, songs=songs, artists=artists)


# ---------------------------------------------------------------------------
# Songs
# ---------------------------------------------------------------------------
@bp.get("/song/<int:song_id>")
def song_detail(song_id: int):
    song = db.query_one("SELECT * FROM dbo.vw_SongDetail WHERE SongID = ?", (song_id,))
    if song is None:
        abort(404)

    # Collaborating artists (Singer + Featured) — used to render names like "PUN, The Toys"
    artists = db.query(
        """
        SELECT a.ArtistID, a.ArtistName, r.[Role]
        FROM dbo.Song_Artist_Role AS sar
        JOIN dbo.Artist AS a ON a.ArtistID = sar.ArtistID
        JOIN dbo.[Role]  AS r ON r.RoleID   = sar.RoleID
        WHERE sar.SongID = ? AND r.[Role] IN (N'Singer', N'Featured')
        ORDER BY CASE r.[Role] WHEN N'Singer' THEN 0 ELSE 1 END, a.ArtistName
        """,
        (song_id,),
    )

    roles = db.query(
        """
        SELECT a.ArtistID, a.ArtistName, r.[Role], r.Role_desc
        FROM dbo.Song_Artist_Role AS sar
        JOIN dbo.Artist AS a ON a.ArtistID = sar.ArtistID
        JOIN dbo.[Role]  AS r ON r.RoleID   = sar.RoleID
        WHERE sar.SongID = ?
        ORDER BY r.RoleID, a.ArtistName
        """,
        (song_id,),
    )

    counts = db.query_one(
        """
        SELECT (SELECT COUNT(*) FROM dbo.Playlist_Detail WHERE SongID = ?) AS InPlaylists,
               (SELECT COUNT(DISTINCT UserID) FROM dbo.History WHERE SongID = ?) AS Listeners,
               (SELECT COUNT(*) FROM dbo.History WHERE SongID = ?) AS Plays
        """,
        (song_id, song_id, song_id),
    )

    # Main artist info + that artist's other songs (shown below the song page)
    main_artist = None
    other_songs = []
    if song["MainArtistID"]:
        main_artist = db.query_one(
            "SELECT ArtistID, ArtistName, Country, Bio FROM dbo.Artist WHERE ArtistID = ?",
            (song["MainArtistID"],),
        )
        other_songs = db.query(
            """
            SELECT TOP (6) *
            FROM dbo.vw_SongDetail
            WHERE SongID IN (SELECT SongID FROM dbo.Song_Artist_Role WHERE ArtistID = ?)
              AND SongID <> ?
            ORDER BY PlayCount DESC, SongTitle
            """,
            (song["MainArtistID"], song_id),
        )

    in_playlists, addable = [], []
    if g.user:
        in_playlists = db.query(
            """
            SELECT ps.PlaylistID, ps.PLname, ps.Song_Amount
            FROM dbo.vw_PlaylistSummary AS ps
            JOIN dbo.Playlist_Detail AS d ON d.PlaylistID = ps.PlaylistID
            WHERE ps.UserID = ? AND d.SongID = ?
            """,
            (g.user["UserID"], song_id),
        )
        addable = db.query(
            """
            SELECT ps.PlaylistID, ps.PLname
            FROM dbo.vw_PlaylistSummary AS ps
            WHERE ps.UserID = ?
              AND NOT EXISTS (SELECT 1 FROM dbo.Playlist_Detail AS d
                              WHERE d.PlaylistID = ps.PlaylistID AND d.SongID = ?)
            ORDER BY ps.PLname
            """,
            (g.user["UserID"], song_id),
        )

    return render_template(
        "song.html",
        song=song,
        artists=artists,
        roles=roles,
        counts=counts,
        main_artist=main_artist,
        other_songs=other_songs,
        in_playlists=in_playlists,
        addable=addable,
    )


# ---------------------------------------------------------------------------
# Artists
# ---------------------------------------------------------------------------
@bp.get("/artist/<int:artist_id>")
def artist_detail(artist_id: int):
    artist = db.query_one("SELECT * FROM dbo.Artist WHERE ArtistID = ?", (artist_id,))
    if artist is None:
        abort(404)

    # STRING_AGG combines this artist's roles per song (SQL Server 2017+)
    songs = db.query(
        """
        SELECT vd.SongID, vd.SongTitle, vd.Duration, vd.PlayCount,
               vd.MainArtistName, vd.Released_Date,
               STRING_AGG(r.[Role], N', ') WITHIN GROUP (ORDER BY r.RoleID) AS Roles
        FROM dbo.Song_Artist_Role AS sar
        JOIN dbo.vw_SongDetail AS vd ON vd.SongID = sar.SongID
        JOIN dbo.[Role] AS r ON r.RoleID = sar.RoleID
        WHERE sar.ArtistID = ?
        GROUP BY vd.SongID, vd.SongTitle, vd.Duration, vd.PlayCount,
                 vd.MainArtistName, vd.Released_Date
        ORDER BY vd.PlayCount DESC, vd.SongTitle
        """,
        (artist_id,),
    )

    collaborators = db.query(
        """
        SELECT TOP (6) a2.ArtistID, a2.ArtistName, COUNT(DISTINCT sar2.SongID) AS SharedSongs
        FROM dbo.Song_Artist_Role AS sar1
        JOIN dbo.Song_Artist_Role AS sar2
             ON sar2.SongID = sar1.SongID AND sar2.ArtistID <> sar1.ArtistID
        JOIN dbo.Artist AS a2 ON a2.ArtistID = sar2.ArtistID
        WHERE sar1.ArtistID = ?
        GROUP BY a2.ArtistID, a2.ArtistName
        ORDER BY SharedSongs DESC, a2.ArtistName
        """,
        (artist_id,),
    )

    return render_template(
        "artist.html", artist=artist, songs=songs, collaborators=collaborators
    )


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------
def _playlist_covers() -> dict[int, int]:
    """Playlist -> SongID of its first song (that cover art becomes the playlist cover)"""
    rows = db.query(
        """
        SELECT PlaylistID, SongID
        FROM (
            SELECT d.PlaylistID, d.SongID,
                   ROW_NUMBER() OVER (PARTITION BY d.PlaylistID ORDER BY d.TrackNo) AS rn
            FROM dbo.Playlist_Detail AS d
        ) AS x
        WHERE rn = 1
        """
    )
    return {row["PlaylistID"]: row["SongID"] for row in rows}


@bp.get("/playlists")
@login_required
def playlists():
    return render_template(
        "playlists.html",
        playlists=_playlists_of(g.user["UserID"]),
        public_playlists=db.query(
            """
            SELECT TOP (12) * FROM dbo.vw_PlaylistSummary
            WHERE UserID <> ?
            ORDER BY Song_Amount DESC, Create_Date DESC
            """,
            (g.user["UserID"],),
        ),
        covers=_playlist_covers(),
    )


@bp.post("/playlists/create")
@login_required
def playlist_create():
    name = (request.form.get("plname") or "").strip()
    if not name:
        flash("กรุณาตั้งชื่อเพลย์ลิสต์ด้วยครับ", "error")
        return redirect(url_for("main.playlists"))

    try:
        rows = db.call_proc(
            """
            DECLARE @new_id INT;
            EXEC dbo.usp_Playlist_Create @UserID = ?, @PLname = ?, @NewPlaylistID = @new_id OUTPUT;
            SELECT @new_id AS NewPlaylistID;
            """,
            (g.user["UserID"], name),
        )
    except pyodbc.Error as exc:
        flash(db.db_message(exc), "error")
        return redirect(url_for("main.playlists"))

    new_id = rows[0]["NewPlaylistID"] if rows else None
    flash(f"สร้างเพลย์ลิสต์ “{name}” แล้ว", "success")
    if new_id:
        return redirect(url_for("main.playlist_detail", playlist_id=new_id))
    return redirect(url_for("main.playlists"))


@bp.get("/playlist/<int:playlist_id>")
def playlist_detail(playlist_id: int):
    summary = db.query_one(
        "SELECT * FROM dbo.vw_PlaylistSummary WHERE PlaylistID = ?", (playlist_id,)
    )
    if summary is None:
        abort(404)

    tracks = db.query(
        "SELECT * FROM dbo.vw_PlaylistTrackList WHERE PlaylistID = ? ORDER BY TrackNo",
        (playlist_id,),
    )

    is_owner = g.user is not None and summary["UserID"] == g.user["UserID"]
    suggestions = []
    if is_owner:
        suggestions = db.query(
            """
            SELECT TOP (10) vd.SongID, vd.SongTitle, vd.MainArtistName, vd.PlayCount
            FROM dbo.vw_SongDetail AS vd
            WHERE NOT EXISTS (SELECT 1 FROM dbo.Playlist_Detail AS d
                              WHERE d.PlaylistID = ? AND d.SongID = vd.SongID)
            ORDER BY vd.PlayCount DESC
            """,
            (playlist_id,),
        )

    return render_template(
        "playlist.html",
        summary=summary,
        tracks=tracks,
        is_owner=is_owner,
        suggestions=suggestions,
    )


@bp.post("/playlist/<int:playlist_id>/add")
@login_required
def playlist_add(playlist_id: int):
    _owned_playlist_or_404(playlist_id)
    song_id = _int_arg("song_id")
    if song_id is None:
        flash("ไม่พบเพลงที่ต้องการเพิ่ม", "error")
        return redirect(url_for("main.playlist_detail", playlist_id=playlist_id))

    try:
        rows = db.call_proc(
            """
            DECLARE @added BIT;
            EXEC dbo.usp_Playlist_AddSong @PlaylistID = ?, @SongID = ?, @Added = @added OUTPUT;
            SELECT CAST(@added AS INT) AS Added;
            """,
            (playlist_id, song_id),
        )
        added = bool(rows and rows[0]["Added"])
        flash("เพิ่มเพลงเข้าเพลย์ลิสต์แล้ว" if added else "เพลงนี้อยู่ในเพลย์ลิสต์แล้ว",
              "success" if added else "warning")
    except pyodbc.Error as exc:
        flash(db.db_message(exc), "error")

    return redirect(request.referrer or url_for("main.playlist_detail", playlist_id=playlist_id))


@bp.post("/playlist/<int:playlist_id>/remove")
@login_required
def playlist_remove(playlist_id: int):
    _owned_playlist_or_404(playlist_id)
    song_id = _int_arg("song_id")
    if song_id is None:
        abort(400)

    try:
        rows = db.call_proc(
            """
            DECLARE @removed BIT;
            EXEC dbo.usp_Playlist_RemoveSong @PlaylistID = ?, @SongID = ?, @Removed = @removed OUTPUT;
            SELECT CAST(@removed AS INT) AS Removed;
            """,
            (playlist_id, song_id),
        )
        if rows and rows[0]["Removed"]:
            flash("ลบเพลงออกจากเพลย์ลิสต์แล้ว", "success")
        else:
            flash("ไม่พบเพลงนี้ในเพลย์ลิสต์", "warning")
    except pyodbc.Error as exc:
        flash(db.db_message(exc), "error")

    return redirect(url_for("main.playlist_detail", playlist_id=playlist_id))


@bp.post("/playlist/<int:playlist_id>/delete")
@login_required
def playlist_delete(playlist_id: int):
    row = _owned_playlist_or_404(playlist_id)
    # Playlist_Detail rows are removed by ON DELETE CASCADE
    db.execute("DELETE FROM dbo.Playlist WHERE PlaylistID = ?", (playlist_id,))
    flash(f"ลบเพลย์ลิสต์ “{row['PLname']}” แล้ว", "success")
    return redirect(url_for("main.playlists"))


# ---------------------------------------------------------------------------
# Listening history
# ---------------------------------------------------------------------------
@bp.get("/history")
@login_required
def history():
    rows = db.query(
        """
        SELECT TOP (100) h.HistoryID, h.Played_At, vd.SongID, vd.SongTitle,
                         vd.MainArtistName, vd.Duration
        FROM dbo.History AS h
        JOIN dbo.vw_SongDetail AS vd ON vd.SongID = h.SongID
        WHERE h.UserID = ?
        ORDER BY h.Played_At DESC
        """,
        (g.user["UserID"],),
    )

    summary = db.query_one(
        """
        SELECT COUNT(*) AS TotalPlays,
               COUNT(DISTINCT h.SongID) AS DistinctSongs,
               ISNULL(SUM(s.Duration), 0) AS TotalSeconds
        FROM dbo.History AS h
        JOIN dbo.Song AS s ON s.SongID = h.SongID
        WHERE h.UserID = ?
        """,
        (g.user["UserID"],),
    )

    top_artists = db.query(
        """
        SELECT TOP (5) vd.MainArtistName, COUNT(*) AS Plays
        FROM dbo.History AS h
        JOIN dbo.vw_SongDetail AS vd ON vd.SongID = h.SongID
        WHERE h.UserID = ?
        GROUP BY vd.MainArtistName
        ORDER BY Plays DESC
        """,
        (g.user["UserID"],),
    )

    return render_template(
        "history.html", rows=rows, summary=summary, top_artists=top_artists
    )


# ---------------------------------------------------------------------------
# API for the player (called via fetch when a song is played / the credits tab is opened)
# ---------------------------------------------------------------------------
ROLE_SHORT_LABEL = {
    "Producer": "โปรดิวเซอร์",
    "Composer": "แต่งเพลง",
    "Lyricist": "เนื้อร้อง",
    "Featured": "ศิลปินรับเชิญ",
    "Singer": "นักร้อง",
}


@bp.get("/api/song/<int:song_id>")
def api_song(song_id: int):
    """Song data + credits (SONG_ARTIST_ROLE) so the full screen can render without navigation"""
    song = db.query_one("SELECT * FROM dbo.vw_SongDetail WHERE SongID = ?", (song_id,))
    if song is None:
        return jsonify(ok=False, reason="ไม่พบเพลงนี้"), 404

    credits = db.query(
        """
        SELECT a.ArtistName, r.[Role],
               ISNULL(NULLIF(r.Role_desc, N''), r.[Role]) AS Label
        FROM dbo.Song_Artist_Role AS sar
        JOIN dbo.Artist AS a ON a.ArtistID = sar.ArtistID
        JOIN dbo.[Role]  AS r ON r.RoleID   = sar.RoleID
        WHERE sar.SongID = ?
        ORDER BY r.RoleID, a.ArtistName
        """,
        (song_id,),
    )
    for row in credits:
        row["ShortLabel"] = ROLE_SHORT_LABEL.get(row["Role"], row["Role"])

    released = song["Released_Date"]
    return jsonify(
        ok=True,
        songId=song["SongID"],
        title=song["SongTitle"],
        artists=song["ArtistList"],
        duration=song["Duration"],
        plays=song["PlayCount"],
        released=released.isoformat() if released else None,
        releasedYearBE=(released.year + 543) if released else None,
        credits=credits,
    )


@bp.post("/api/play/<int:song_id>")
def api_play(song_id: int):
    if g.user is None:
        return jsonify(ok=False, reason="ต้องเข้าสู่ระบบก่อนจึงจะบันทึกประวัติการฟัง"), 401

    try:
        rows = db.call_proc(
            """
            EXEC dbo.usp_History_Record @UserID = ?, @SongID = ?;
            SELECT PlayCount FROM dbo.Song WHERE SongID = ?;
            """,
            (g.user["UserID"], song_id, song_id),
        )
    except pyodbc.Error as exc:
        return jsonify(ok=False, reason=db.db_message(exc)), 400

    if not rows:
        return jsonify(ok=False, reason="ไม่พบเพลงนี้"), 404

    return jsonify(ok=True, songId=song_id, playCount=rows[0]["PlayCount"])


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
        password = f.get("password") or ""
        email = (f.get("email") or "").strip().lower()
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


# ---------------------------------------------------------------------------
# Profile menu pages: account settings, help, legal
# ---------------------------------------------------------------------------
SETTINGS_TABS = ("general", "account", "about")


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
    return {"user": user, "stats": stats, "tab": tab, "tabs": SETTINGS_TABS}


@bp.get("/settings")
@login_required
def settings():
    """Settings has its own sub-pages; the bare URL opens General"""
    return redirect(url_for("main.settings_tab", tab="general"))


@bp.get("/settings/<tab>")
@login_required
def settings_tab(tab: str):
    if tab not in SETTINGS_TABS:
        abort(404)
    return render_template(f"settings_{tab}.html", **_settings_context(tab))


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




