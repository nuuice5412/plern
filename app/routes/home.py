
"""Home page, song list, artist list and search"""
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
# Home page
# ---------------------------------------------------------------------------
@bp.get("/")
def index():
    top_songs = db.query("SELECT TOP (20) * FROM dbo.vw_TopSongs")

    artists = db.query(artist_list_sql(20))

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
               (SELECT COUNT(DISTINCT sar.ArtistID) FROM dbo.Song_Artist_Role sar
                    JOIN dbo.[Role] r ON r.RoleID = sar.RoleID
                   WHERE r.[Role] IN (N'Singer', N'Featured')) AS Artists,
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
# Only artists who actually perform (Singer / Featured). Songwriters that came from
# MusicBrainz still appear on the song pages, but they are not "artists" in the listing.
def artist_list_sql(limit: int | None = None) -> str:
    top = f"TOP ({int(limit)}) " if limit else ""
    return f"""
    WITH performed AS (
        SELECT sar.ArtistID, sar.SongID
        FROM dbo.Song_Artist_Role AS sar
        JOIN dbo.[Role] AS r ON r.RoleID = sar.RoleID
        WHERE r.[Role] IN (N'Singer', N'Featured')
        GROUP BY sar.ArtistID, sar.SongID
    )
    SELECT {top}a.ArtistID, a.ArtistName, a.Country,
           COUNT(p.SongID) AS SongCount,
           ISNULL(SUM(s.PlayCount), 0) AS TotalPlays
    FROM dbo.Artist AS a
    JOIN performed AS p ON p.ArtistID = a.ArtistID
    JOIN dbo.Song AS s ON s.SongID = p.SongID
    GROUP BY a.ArtistID, a.ArtistName, a.Country
    ORDER BY TotalPlays DESC, a.ArtistName
    """


ARTIST_LIST_SQL = artist_list_sql()


SONGS_PER_PAGE = 50


@bp.get("/songs")
def all_songs():
    """All songs, paginated (50 per page). ?sort=new orders by release date."""
    sort = (request.args.get("sort") or "top").lower()
    page = max(1, int(request.args.get("page") or 1))

    if sort == "new":
        total = db.query_one(
            "SELECT COUNT(*) AS n FROM dbo.vw_SongDetail WHERE Released_Date IS NOT NULL"
        )["n"]
        heading = "เพลงออกใหม่"
        order = "ORDER BY Released_Date DESC, SongID DESC"
        where = "WHERE Released_Date IS NOT NULL"
    else:
        total = db.query_one("SELECT COUNT(*) AS n FROM dbo.vw_SongDetail")["n"]
        heading = "เพลงทั้งหมด"
        order = "ORDER BY PlayCount DESC, SongTitle"
        where = ""

    pages = max(1, -(-total // SONGS_PER_PAGE))
    page = min(page, pages)
    offset = (page - 1) * SONGS_PER_PAGE

    songs = db.query(
        f"SELECT * FROM dbo.vw_SongDetail {where} {order} "
        "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        (offset, SONGS_PER_PAGE),
    )

    return render_template(
        "songs.html",
        songs=songs,
        heading=heading,
        subtitle=f"ทั้งหมด {total} เพลง" if sort != "new" else f"ทั้งหมด {total} เพลง (ใหม่สุดก่อน)",
        page=page,
        pages=pages,
        total=total,
        start=offset + 1,
        sort=sort,
    )


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


