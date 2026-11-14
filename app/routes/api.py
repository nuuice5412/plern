
"""JSON endpoints the player uses"""
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


