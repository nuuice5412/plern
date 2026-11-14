
"""Playlist list, detail and CRUD"""
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


