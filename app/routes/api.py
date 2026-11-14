
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

@bp.get("/api/suggest")
def api_suggest():
    """Type-ahead for the search box: matching songs + artists (prefix first)."""
    raw = (request.args.get("q") or "").strip()
    if not raw:
        return jsonify({"q": "", "songs": [], "artists": []})
    if len(raw) > 60:
        raw = raw[:60]

    like_prefix = raw + "%"
    like_any = "%" + raw + "%"
    try:
        songs = db.query(
            """
            SELECT TOP (6) SongID, SongTitle, MainArtistName
            FROM dbo.vw_SongDetail
            WHERE SongTitle LIKE ?
            ORDER BY CASE WHEN SongTitle LIKE ? THEN 0 ELSE 1 END,
                     PlayCount DESC, SongTitle
            """,
            (like_any, like_prefix),
        )
        artists = db.query(
            """
            SELECT TOP (4) a.ArtistID, a.ArtistName
            FROM dbo.Artist AS a
            WHERE a.ArtistName LIKE ?
              AND EXISTS (
                  SELECT 1
                  FROM dbo.Song_Artist_Role AS sar
                  JOIN dbo.[Role] AS r ON r.RoleID = sar.RoleID
                  WHERE sar.ArtistID = a.ArtistID AND r.[Role] IN (N'Singer', N'Featured'))
            ORDER BY CASE WHEN a.ArtistName LIKE ? THEN 0 ELSE 1 END, a.ArtistName
            """,
            (like_any, like_prefix),
        )
    except Exception:                      # noqa: BLE001 - suggestions must never 500
        return jsonify({"q": raw, "songs": [], "artists": []})

    return jsonify({
        "q": raw,
        "songs": [{"id": s["SongID"], "title": s["SongTitle"],
                   "artist": s["MainArtistName"]} for s in songs],
        "artists": [{"id": a["ArtistID"], "name": a["ArtistName"]} for a in artists],
    })
