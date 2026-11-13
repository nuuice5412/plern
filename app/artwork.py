"""
artwork.py - อ่าน manifest ของรูปภาพ (ปกเพลง/รูปศิลปิน) มาให้ template ใช้

ไฟล์รูปถูกสร้างโดย tools/fetch_artwork.py
    app/static/img/cover_<SongID>.jpg
    app/static/img/artist_<ArtistID>.jpg
    app/static/img/manifest.json

ทำไมใช้ manifest ไม่เพิ่มคอลัมน์ใน DB: เพื่อไม่ให้ schema หลุดจาก ER ของกลุ่ม
template จะเรียก cover_url(song_id) / artist_photo_url(artist_id)
ถ้าไม่มีรูป จะคืน None แล้ว macro จะ fallback ไปเป็น gradient + ตัวอักษร
"""
from __future__ import annotations

import json
import pathlib

from flask import current_app, url_for

# cache 1 ชุดต่อ process — เช็ค mtime เพื่อให้เห็นไฟล์ใหม่หลังรัน fetch_artwork
_state: dict = {"mtime": None, "data": {"covers": {}, "artists": {}}}
_EMPTY = {"covers": {}, "artists": {}}


def _manifest_path() -> pathlib.Path:
    return pathlib.Path(current_app.static_folder) / "img" / "manifest.json"


def _load() -> dict:
    path = _manifest_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return _EMPTY

    if _state["mtime"] != mtime:
        try:
            _state["data"] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _state["data"] = _EMPTY
        _state["mtime"] = mtime

    return _state["data"]


def cover_url(song_id) -> str | None:
    name = _load().get("covers", {}).get(str(song_id))
    return url_for("static", filename=f"img/{name}") if name else None


def artist_photo_url(artist_id) -> str | None:
    name = _load().get("artists", {}).get(str(artist_id))
    return url_for("static", filename=f"img/{name}") if name else None
