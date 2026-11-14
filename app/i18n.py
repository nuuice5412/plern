"""
i18n.py - tiny translation layer for the app chrome

Only the shared shell is translated (sidebar, top bar, profile menu and the
settings/help/legal pages). Song titles, artist names and other content stay
as they are, because they are real data from the database.

Add a string: put it in both dictionaries below, then call t('key') in a template.
"""
from __future__ import annotations

from flask import session

DEFAULT = "th"

STRINGS: dict[str, dict[str, str]] = {
    "th": {
        "nav.home": "หน้าแรก",
        "nav.playlists": "คลังเพลย์ลิสต์",
        "nav.history": "ประวัติการฟัง",
        "search.placeholder": "ค้นหาเพลง หรือศิลปิน…",
        "menu.settings": "ตั้งค่า",
        "menu.help": "ช่วยเหลือ",
        "menu.terms": "ข้อกำหนดและความเป็นส่วนตัว",
        "menu.logout": "ออกจากระบบ",
        "settings.eyebrow": "บัญชีของฉัน",
        "settings.title": "ตั้งค่า",
        "settings.sub": "ข้อมูลบัญชี การใช้งาน และการตั้งค่าทั่วไป",
        "settings.account": "ข้อมูลส่วนตัว",
        "settings.usage": "การใช้งาน",
        "settings.actions": "บัญชี",
        "settings.preferences": "การตั้งค่า",
        "settings.language": "ภาษา",
        "settings.language_hint": "เปลี่ยนภาษาของเมนูและหน้าตั้งค่า",
        "settings.save": "บันทึก",
        "settings.saved": "บันทึกการตั้งค่าแล้ว",
        "settings.playlists": "เพลย์ลิสต์",
        "settings.tracks": "เพลงในเพลย์ลิสต์",
        "settings.plays": "ครั้งที่ฟัง",
        "settings.time": "เวลาฟังรวม",
        "settings.view_history": "ดูประวัติการฟัง",
        "settings.go_playlists": "ไปที่คลังเพลย์ลิสต์",
        "settings.logout": "ออกจากระบบ",
        "field.username": "ชื่อผู้ใช้",
        "field.email": "อีเมล",
        "field.gender": "เพศ",
        "field.dob": "วันเกิด",
        "field.country": "ประเทศ",
        "field.tel": "เบอร์โทร",
        "help.eyebrow": "ช่วยเหลือ",
        "help.title": "คู่มือการใช้งาน",
        "help.sub": "คีย์ลัดและวิธีใช้เครื่องเล่นเพลง",
        "help.keys": "คีย์ลัด",
        "help.faq": "คำถามที่พบบ่อย",
        "terms.eyebrow": "ข้อกำหนด",
        "terms.title": "ข้อกำหนดและความเป็นส่วนตัว",
        "terms.sub": "โปรเจกต์วิชา Database — ใช้เพื่อการสาธิตเท่านั้น",
    },
    "en": {
        "nav.home": "Home",
        "nav.playlists": "Collection",
        "nav.history": "History",
        "search.placeholder": "Search songs or artists…",
        "menu.settings": "Settings",
        "menu.help": "Help",
        "menu.terms": "Terms & privacy",
        "menu.logout": "Log out",
        "settings.eyebrow": "My account",
        "settings.title": "Settings",
        "settings.sub": "Account details, usage and general preferences",
        "settings.account": "Profile",
        "settings.usage": "Usage",
        "settings.actions": "Account",
        "settings.preferences": "Preferences",
        "settings.language": "Language",
        "settings.language_hint": "Changes the language of the menu and settings pages",
        "settings.save": "Save",
        "settings.saved": "Preferences saved",
        "settings.playlists": "Playlists",
        "settings.tracks": "Tracks in playlists",
        "settings.plays": "Plays",
        "settings.time": "Listening time",
        "settings.view_history": "View history",
        "settings.go_playlists": "Go to collection",
        "settings.logout": "Log out",
        "field.username": "Username",
        "field.email": "Email",
        "field.gender": "Gender",
        "field.dob": "Date of birth",
        "field.country": "Country",
        "field.tel": "Phone",
        "help.eyebrow": "Help",
        "help.title": "How to use",
        "help.sub": "Keyboard shortcuts and player tips",
        "help.keys": "Keyboard shortcuts",
        "help.faq": "Frequently asked",
        "terms.eyebrow": "Terms",
        "terms.title": "Terms & privacy",
        "terms.sub": "Database course project — demo use only",
    },
}

SUPPORTED = tuple(STRINGS.keys())


def current_language() -> str:
    lang = session.get("lang")
    return lang if lang in STRINGS else DEFAULT


def translate(key: str) -> str:
    lang = current_language()
    return STRINGS.get(lang, STRINGS[DEFAULT]).get(key, STRINGS[DEFAULT].get(key, key))
