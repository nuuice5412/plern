"""Shared helpers used by every route module"""
from __future__ import annotations

import re

from flask import abort, g, request

from .. import db

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

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

