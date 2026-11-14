"""Blueprint `main`: the whole app, split into small modules.

    home        /, /songs, /artists, /search
    catalog     /song/<id>, /artist/<id>
    playlists   /playlists, /playlist/<id>
    history     /history
    api         JSON for the player
    auth_routes /login, /register, /logout
    settings    /settings*, /help, /terms, /sw.js
    errors      403 / 404
"""
from flask import Blueprint

bp = Blueprint("main", __name__)

from . import common, home, catalog, playlists, history, api, auth_routes, settings, errors  # noqa: E402,F401
