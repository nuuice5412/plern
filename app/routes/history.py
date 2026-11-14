
"""Listening history"""
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


