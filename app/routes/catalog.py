
"""Song and artist detail pages"""
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


