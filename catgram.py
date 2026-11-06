#!/usr/bin/env python3
"""catgram — маленький клиент Telegram для Linux (PyQt6 + Telethon)."""
import asyncio
import hashlib
import html
import inspect
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from string import Template

import qasync
from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QAction, QColor, QDesktopServices, QIcon, QImage, QImageReader, QKeySequence, QPainter,
    QPainterPath, QPen, QPixmap,
    QPolygonF, QShortcut, QTextCursor, QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget,
    QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)
from telethon import TelegramClient, events, functions, types
from telethon.errors import (
    PasswordHashInvalidError, PhoneCodeInvalidError, PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.utils import get_display_name

APP = "catgram"
VERSION = "0.7.3"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / APP
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP
AVATAR_DIR = CACHE_DIR / "avatars"   # кэш аватарок (обновляется раз в неделю)
CONFIG_FILE = CONFIG_DIR / "config.json"       # api_id / api_hash
SETTINGS_FILE = CONFIG_DIR / "settings.json"   # настройки интерфейса
PAGE = 50        # сообщений при открытии чата
PAGE_OLD = 100   # сообщений за один запрос при прокрутке вверх
PHOTO_PX = 400   # фото в чате качаем не крупнее этого (у Telegram есть 320 и 800 px)
STICKER_PX = 160   # ширина стикера в чате

# Впиши сюда СВОИ ключи с my.telegram.org (API development tools) —
# тогда catgram никогда не будет их спрашивать.
API_ID = 0
API_HASH = ""


# ---------- языки ----------

LANGS = {"ru": "Русский", "en": "English", "uk": "Українська"}

TEXT = {
    "en": {
        "title": "🐱 catgram",
        "login": "🐱 catgram — sign in",
        "api_id": "api_id (my.telegram.org → API development tools):",
        "api_hash": "api_hash:",
        "phone": "Phone number (+country code and number):",
        "bad_phone": "Invalid number. Use international format: +<country code><number> "
                     "(no leading 0), e.g. +12025550123",
        "code": "Code from Telegram:",
        "bad_code": "Wrong code, try again:",
        "pw": "Two-step verification password:",
        "bad_pw": "Wrong password, try again:",
        "write": "Meow… type a message and press Enter",
        "find_chats": "Search chats…",
        "find_msgs": "Search in this chat… (Enter — search, Esc — close)",
        "pick_chat": "Pick a chat on the left",
        "menu": "catgram",
        "settings": "Settings…",
        "search": "Search in chat",
        "updates": "Check for updates",
        "quit": "Quit",
        "me": "Me",
        "m_sticker": "[sticker]", "m_photo": "[photo]", "m_voice": "[voice]",
        "m_video": "[video]", "m_file": "[file]", "m_other": "[attachment]",
        "set_title": "Settings",
        "set_lang": "Language",
        "set_theme": "Theme",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "set_font": "Font size",
        "set_avatars": "Avatars",
        "av_real": "Real photos (cat if none)",
        "av_cats": "Cats only",
        "av_none": "None",
        "set_photos": "Show pictures in chat",
        "info": "Chat info",
        "about": "Description",
        "username": "Username",
        "phone_lbl": "Phone",
        "members": "Members",
        "set_upd_start": "Check for updates on start",
        "set_upd_url": "Updates URL (https)",
        "upd_no_url": "No updates URL set. Add it in Settings.",
        "upd_latest": "You have the latest version.",
        "upd_new": "New version available",
        "upd_err": "Could not check for updates",
        "res": "Search results",
        "nothing": "Nothing found",
        "online": "purring",
        "attach_video": "Send a video",
        "pick_video": "Choose a video",
        "video_files": "Video",
        "all_files": "All files",
        "sending_video": "Sending video",
        "offline": "not purring",
        "hist_start": "· beginning of the conversation ·",
        "hist_loading": "Loading history…",
        "error": "Error",
        "games": "🎮 Games",
        "snake": "🐍 Snake",
        "g2048": "🐾 2048",
        "emoji": "Emoji",
        "score": "Score",
        "best": "Best",
        "game_over": "Game over",
        "paused": "Paused",
        "again": "Press R to play again",
        "game_hint": "Space — pause · R — new game",
        "wait_hint": "Play while you wait for a reply 🐾",
        "stickers": "Stickers",
        "st_load": "Loading stickers…",
        "st_none": "No sticker sets",
        "st_fail": "Couldn't load previews",
        "st_webp": "This Qt build can't read WebP — stickers won't show. "
                   "Install dwebp (package libwebp-tools), ffmpeg or ImageMagick",
        "call": "Call in Telegram",
        "call_tel": "Call phone number (tel:)",
        "call_title": "Call",
        "call_need_lib": "Calls need the ntgcalls library.<br>Install it: "
                         "<code>pip install ntgcalls</code>",
        "call_no_audio": "No microphone or speaker found",
        "call_hint_throw": "Couldn't get the audio device list: {err}",
        "call_hint_libs": "System sound libraries weren't found. Install them and restart "
                          "catgram:\nDebian/Ubuntu: sudo apt install libpulse0 libasound2\n"
                          "Fedora: sudo dnf install pulseaudio-libs alsa-lib\n"
                          "Arch: sudo pacman -S libpulse alsa-lib\n"
                          "Check in the terminal: ldconfig -p | grep libpulse",
        "call_hint_server": "The sound server (PulseAudio/PipeWire) isn't reachable from "
                            "this session. Start catgram from a regular desktop terminal "
                            "(not over SSH, not via sudo) and check that sound works.",
        "call_hint_pactl": "The sound server seems to be running, but ntgcalls sees no "
                           "devices. Run in the same terminal: pactl list short — and "
                           "send the output to the developer.",
        "call_hint_mic": "No microphone is visible (speakers were found). Plug in a "
                         "microphone or enable it in the system sound settings.",
        "call_hint_spk": "No speakers are visible (a microphone was found). Check the "
                         "output devices in the system sound settings.",
        "call_bad_lib": "The installed ntgcalls {ver} doesn't fit: missing {missing}.<br>"
                        "Try <code>pip install -U ntgcalls</code> (in the same environment "
                        "catgram runs in). If that doesn't help, send this text to the "
                        "developer:<br>{have}",
        "call_busy": "Another call is in progress",
        "call_no_phone": "The phone number isn't visible (privacy settings)",
        "call_people_only": "Calls are only available in chats with people",
        "call_tel_fail": "No app handles tel: links. Install one (e.g. KDE Connect / "
                         "GSConnect) or dial the number manually.",
        "call_dialing": "Calling…",
        "call_incoming": "Incoming call…",
        "call_connecting": "Connecting…",
        "call_talking": "On the call",
        "call_accept": "Accept",
        "call_decline": "Decline",
        "call_end": "End call",
        "call_mute": "Mute microphone",
        "call_unmute": "Unmute microphone",
        "call_ended": "Call ended",
        "call_missed": "No answer",
        "call_peer_busy": "Declined or busy",
        "call_failed": "Connection lost",
    },
    "ru": {
        "title": "🐱 catgram",
        "login": "🐱 catgram — вход",
        "api_id": "api_id (my.telegram.org → API development tools):",
        "api_hash": "api_hash:",
        "phone": "Номер телефона (+код страны и номер):",
        "bad_phone": "Номер не подошёл. Нужен международный формат: "
                     "+<код страны><номер> (без ведущего 0), например +12025550123",
        "code": "Код из Telegram:",
        "bad_code": "Неверный код, попробуйте ещё раз:",
        "pw": "Пароль двухфакторной защиты:",
        "bad_pw": "Неверный пароль, ещё раз:",
        "write": "Мяу… напиши сообщение и нажми Enter",
        "find_chats": "Поиск чатов…",
        "find_msgs": "Поиск в чате… (Enter — искать, Esc — закрыть)",
        "pick_chat": "Выберите чат слева",
        "menu": "catgram",
        "settings": "Настройки…",
        "search": "Поиск в чате",
        "updates": "Проверить обновления",
        "quit": "Выход",
        "me": "Я",
        "m_sticker": "[стикер]", "m_photo": "[фото]", "m_voice": "[голосовое]",
        "m_video": "[видео]", "m_file": "[файл]", "m_other": "[вложение]",
        "set_title": "Настройки",
        "set_lang": "котязык",
        "set_theme": "Тема",
        "theme_dark": "Тёмная",
        "theme_light": "Светлая",
        "set_font": "Размер шрифта",
        "set_avatars": "Аватарки",
        "av_real": "Настоящие фото (кот, если нет)",
        "av_cats": "Только котики",
        "av_none": "Без аватарок",
        "set_photos": "Показывать картинки в чате",
        "info": "Информация о чате",
        "about": "Описание",
        "username": "Имя пользователя",
        "phone_lbl": "Телефон",
        "members": "Участников",
        "set_upd_start": "Проверять обновления при запуске",
        "set_upd_url": "Адрес обновлений (https)",
        "upd_no_url": "Адрес обновлений не задан. Укажите его в настройках.",
        "upd_latest": "У вас последняя версия.",
        "upd_new": "Доступна новая версия",
        "upd_err": "Не удалось проверить обновления",
        "res": "Результаты поиска",
        "nothing": "Ничего не накотено",
        "online": "котится",
        "attach_video": "Отправить видео",
        "pick_video": "Выберите видео",
        "video_files": "Видео",
        "all_files": "Все файлы",
        "sending_video": "Отправляю видео",
        "offline": "не котится",
        "hist_start": "· начало переписки ·",
        "hist_loading": "Загружаю историю…",
        "error": "Ошибка",
        "games": "🎮 Игры",
        "snake": "🐍 Змейка",
        "g2048": "🐾 2048",
        "emoji": "Смайлики",
        "score": "Счёт",
        "best": "Рекорд",
        "game_over": "Игра окончена",
        "paused": "Пауза",
        "again": "Нажмите R, чтобы сыграть ещё раз",
        "game_hint": "Пробел — пауза · R — заново",
        "wait_hint": "Сыграйте, пока ждёте ответа 🐾",
        "stickers": "Стикеры",
        "st_load": "Загружаю стикеры…",
        "st_none": "Нет наборов стикеров",
        "st_fail": "Не удалось загрузить превью",
        "st_webp": "Эта сборка Qt не читает WebP — стикеры не покажутся. "
                   "Установите dwebp (пакет libwebp-tools), ffmpeg или ImageMagick",
        "call": "Позвонить в Telegram",
        "call_tel": "Позвонить по номеру (tel:)",
        "call_title": "Звонок",
        "call_need_lib": "Для звонков нужна библиотека ntgcalls.<br>Установите: "
                         "<code>pip install ntgcalls</code>",
        "call_no_audio": "Не найден микрофон или динамики",
        "call_hint_throw": "Не удалось получить список звуковых устройств: {err}",
        "call_hint_libs": "Системные библиотеки звука не нашлись. Установите их и "
                          "перезапустите catgram:\nDebian/Ubuntu: sudo apt install "
                          "libpulse0 libasound2\nFedora: sudo dnf install pulseaudio-libs "
                          "alsa-lib\nArch: sudo pacman -S libpulse alsa-lib\n"
                          "Проверка в терминале: ldconfig -p | grep libpulse",
        "call_hint_server": "Звуковой сервер (PulseAudio/PipeWire) не доступен из этого "
                            "окружения. Запустите catgram из обычного терминала "
                            "десктоп-сессии (не по SSH и не через sudo) и убедитесь, что "
                            "звук в системе работает.",
        "call_hint_pactl": "Звуковой сервер вроде работает, но ntgcalls не видит "
                           "устройств. Выполните в том же терминале: pactl list short — "
                           "и пришлите вывод разработчику.",
        "call_hint_mic": "Микрофон не виден (динамики нашлись). Подключите микрофон или "
                         "включите его в настройках звука системы.",
        "call_hint_spk": "Динамики не видны (микрофон нашёлся). Проверьте устройства "
                         "вывода в настройках звука системы.",
        "call_bad_lib": "Установленная ntgcalls {ver} не подходит: нет {missing}.<br>"
                        "Попробуйте <code>pip install -U ntgcalls</code> (в том же окружении, "
                        "где запускается catgram). Если не поможет — пришлите разработчику "
                        "этот текст:<br>{have}",
        "call_busy": "Уже идёт другой звонок",
        "call_no_phone": "Номер телефона не виден (настройки приватности)",
        "call_people_only": "Звонить можно только в чатах с людьми",
        "call_tel_fail": "Нет приложения для ссылок tel:. Поставьте любое (например, "
                         "KDE Connect / GSConnect) или наберите номер вручную.",
        "call_dialing": "Вызываю…",
        "call_incoming": "Входящий звонок…",
        "call_connecting": "Соединяю…",
        "call_talking": "Разговор",
        "call_accept": "Принять",
        "call_decline": "Отклонить",
        "call_end": "Завершить",
        "call_mute": "Выключить микрофон",
        "call_unmute": "Включить микрофон",
        "call_ended": "Звонок завершён",
        "call_missed": "Не ответили",
        "call_peer_busy": "Отклонён или занято",
        "call_failed": "Связь потеряна",
    },
    "uk": {
        "title": "🐱 catgram",
        "login": "🐱 catgram — вхід",
        "api_id": "api_id (my.telegram.org → API development tools):",
        "api_hash": "api_hash:",
        "phone": "Номер телефону (+код країни та номер):",
        "bad_phone": "Номер не підійшов. Потрібен міжнародний формат: "
                     "+<код країни><номер> (без початкового 0), наприклад +12025550123",
        "code": "Код із Telegram:",
        "bad_code": "Невірний код, спробуйте ще раз:",
        "pw": "Пароль двоетапної перевірки:",
        "bad_pw": "Невірний пароль, ще раз:",
        "write": "Няв… напишіть повідомлення й натисніть Enter",
        "find_chats": "Пошук чатів…",
        "find_msgs": "Пошук у чаті… (Enter — шукати, Esc — закрити)",
        "pick_chat": "Оберіть чат ліворуч",
        "menu": "catgram",
        "settings": "Налаштування…",
        "search": "Пошук у чаті",
        "updates": "Перевірити оновлення",
        "quit": "Вийти",
        "me": "Я",
        "m_sticker": "[стікер]", "m_photo": "[фото]", "m_voice": "[голосове]",
        "m_video": "[відео]", "m_file": "[файл]", "m_other": "[вкладення]",
        "set_title": "Налаштування",
        "set_lang": "Мова",
        "set_theme": "Тема",
        "theme_dark": "Темна",
        "theme_light": "Світла",
        "set_font": "Розмір шрифту",
        "set_avatars": "Аватарки",
        "av_real": "Справжні фото (кіт, якщо немає)",
        "av_cats": "Лише котики",
        "av_none": "Без аватарок",
        "set_photos": "Показувати зображення в чаті",
        "info": "Інформація про чат",
        "about": "Опис",
        "username": "Ім’я користувача",
        "phone_lbl": "Телефон",
        "members": "Учасників",
        "set_upd_start": "Перевіряти оновлення під час запуску",
        "set_upd_url": "Адреса оновлень (https)",
        "upd_no_url": "Адресу оновлень не вказано. Задайте її в налаштуваннях.",
        "upd_latest": "У вас остання версія.",
        "upd_new": "Доступна нова версія",
        "upd_err": "Не вдалося перевірити оновлення",
        "res": "Результати пошуку",
        "nothing": "Нічого не знайдено",
        "online": "котиться",
        "attach_video": "Надіслати відео",
        "pick_video": "Виберіть відео",
        "video_files": "Відео",
        "all_files": "Усі файли",
        "sending_video": "Надсилаю відео",
        "offline": "не котиться",
        "hist_start": "· початок листування ·",
        "hist_loading": "Завантажую історію…",
        "error": "Помилка",
        "games": "🎮 Ігри",
        "snake": "🐍 Змійка",
        "g2048": "🐾 2048",
        "emoji": "Смайлики",
        "score": "Рахунок",
        "best": "Рекорд",
        "game_over": "Гру завершено",
        "paused": "Пауза",
        "again": "Натисніть R, щоб зіграти ще раз",
        "game_hint": "Пробіл — пауза · R — заново",
        "wait_hint": "Пограйте, поки чекаєте відповіді 🐾",
        "stickers": "Стікери",
        "st_load": "Завантажую стікери…",
        "st_none": "Немає наборів стікерів",
        "st_fail": "Не вдалося завантажити прев’ю",
        "st_webp": "Ця збірка Qt не читає WebP — стікери не відобразяться. "
                   "Встановіть dwebp (пакет libwebp-tools), ffmpeg або ImageMagick",
        "call": "Подзвонити в Telegram",
        "call_tel": "Подзвонити за номером (tel:)",
        "call_title": "Дзвінок",
        "call_need_lib": "Для дзвінків потрібна бібліотека ntgcalls.<br>Встановіть: "
                         "<code>pip install ntgcalls</code>",
        "call_no_audio": "Не знайдено мікрофон або динаміки",
        "call_hint_throw": "Не вдалося отримати список звукових пристроїв: {err}",
        "call_hint_libs": "Системних бібліотек звуку не знайдено. Встановіть їх і "
                          "перезапустіть catgram:\nDebian/Ubuntu: sudo apt install "
                          "libpulse0 libasound2\nFedora: sudo dnf install pulseaudio-libs "
                          "alsa-lib\nArch: sudo pacman -S libpulse alsa-lib\n"
                          "Перевірка в терміналі: ldconfig -p | grep libpulse",
        "call_hint_server": "Звуковий сервер (PulseAudio/PipeWire) недоступний із цього "
                            "середовища. Запустіть catgram зі звичайного термінала "
                            "стільничного сеансу (не через SSH і не через sudo) і "
                            "переконайтеся, що звук у системі працює.",
        "call_hint_pactl": "Звуковий сервер, здається, працює, але ntgcalls не бачить "
                           "пристроїв. Виконайте в тому ж терміналі: pactl list short — "
                           "і надішліть вивід розробникові.",
        "call_hint_mic": "Мікрофона не видно (динаміки знайшлися). Підключіть мікрофон "
                         "або увімкніть його в налаштуваннях звуку системи.",
        "call_hint_spk": "Динаміків не видно (мікрофон знайшовся). Перевірте пристрої "
                         "виводу в налаштуваннях звуку системи.",
        "call_bad_lib": "Встановлена ntgcalls {ver} не підходить: немає {missing}.<br>"
                        "Спробуйте <code>pip install -U ntgcalls</code> (у тому ж середовищі, "
                        "де запускається catgram). Якщо не допоможе — надішліть розробникові "
                        "цей текст:<br>{have}",
        "call_busy": "Уже триває інший дзвінок",
        "call_no_phone": "Номер телефону не видно (налаштування приватності)",
        "call_people_only": "Дзвонити можна лише в чатах з людьми",
        "call_tel_fail": "Немає застосунку для посилань tel:. Встановіть будь-який "
                         "(наприклад, KDE Connect / GSConnect) або наберіть номер вручну.",
        "call_dialing": "Викликаю…",
        "call_incoming": "Вхідний дзвінок…",
        "call_connecting": "З’єдную…",
        "call_talking": "Розмова",
        "call_accept": "Прийняти",
        "call_decline": "Відхилити",
        "call_end": "Завершити",
        "call_mute": "Вимкнути мікрофон",
        "call_unmute": "Увімкнути мікрофон",
        "call_ended": "Дзвінок завершено",
        "call_missed": "Не відповіли",
        "call_peer_busy": "Відхилено або зайнято",
        "call_failed": "Зв’язок втрачено",
    },
}


def detect_lang():
    code = (os.environ.get("LC_ALL") or os.environ.get("LANG") or "").lower()
    for lang in ("uk", "ru", "en"):
        if code.startswith(lang):
            return lang
    return "ru"


# ---------- настройки ----------

PALETTES = {
    "dark": dict(bg="#24273a", panel="#1e2030", text="#cad3f5", input="#363a4f",
                 border="#494d64", accent="#f5a97f", accent_text="#1e2030",
                 out="#f5a97f", inn="#8aadf4", dim="#6e738d"),
    "light": dict(bg="#eff1f5", panel="#e6e9ef", text="#4c4f69", input="#ccd0da",
                  border="#bcc0cc", accent="#fe640b", accent_text="#ffffff",
                  out="#d65a10", inn="#1e66f5", dim="#7c7f93"),
}

DEFAULT_SETTINGS = {
    "lang": detect_lang(),
    "theme": "dark",
    "font_size": 14,
    "avatar_mode": "real",   # real | cats | none
    "show_photos": True,
    "check_updates": False,
    "update_url": "",
    "best_snake": 0,         # рекорд в змейке
    "best_2048": 0,          # рекорд в 2048
}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(SETTINGS_FILE.read_text())
        if isinstance(data, dict):
            s.update({k: v for k, v in data.items() if k in s})
    except (OSError, ValueError):
        pass
    if s["lang"] not in LANGS:
        s["lang"] = DEFAULT_SETTINGS["lang"]
    if s["theme"] not in PALETTES:
        s["theme"] = "dark"
    try:
        s["font_size"] = max(10, min(24, int(s["font_size"])))
    except (TypeError, ValueError):
        s["font_size"] = 14
    if s["avatar_mode"] not in ("real", "cats", "none"):
        s["avatar_mode"] = "real"
    for k in ("best_snake", "best_2048"):
        try:
            s[k] = max(0, int(s[k]))
        except (TypeError, ValueError):
            s[k] = 0
    s["show_photos"] = bool(s["show_photos"])
    s["check_updates"] = bool(s["check_updates"])
    s["update_url"] = str(s["update_url"])
    return s


def save_settings():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    SETTINGS_FILE.write_text(json.dumps(S, ensure_ascii=False, indent=2))


S = load_settings()


def tr(key):
    return TEXT.get(S["lang"], TEXT["en"]).get(key) or TEXT["en"][key]


def pal():
    return PALETTES[S["theme"]]


QSS = Template("""
QWidget { background: $bg; color: $text; font-size: ${size}px; }
QListWidget { background: $panel; border: none; }
QListWidget::item { padding: 6px 8px; }
QListWidget::item:selected { background: $accent; color: $accent_text; }
QTextBrowser { background: $bg; border: none; padding: 8px; }
QLineEdit, QSpinBox, QComboBox {
    background: $input; border: 1px solid $border; border-radius: 8px; padding: 6px 8px;
}
QLineEdit:focus { border-color: $accent; }
QMenuBar, QMenu, QStatusBar { background: $panel; }
QMenu::item:selected, QMenuBar::item:selected { background: $accent; color: $accent_text; }
QPushButton {
    background: $input; border: 1px solid $border; border-radius: 8px; padding: 6px 14px;
}
QPushButton:hover { border-color: $accent; }
QPushButton:disabled { background: $panel; color: $dim; border-color: $panel; }
QPushButton#header {
    text-align: left; border: none; border-radius: 0; background: $panel;
    padding: 6px 10px; font-weight: bold;
}
QPushButton#header:hover { background: $input; }
""")


def make_style():
    return QSS.substitute(pal(), size=S["font_size"])


# ---------- коты ----------

FUR = ["#f5a97f", "#8aadf4", "#a6da95", "#c6a0f6", "#eed49f",
       "#ed8796", "#8bd5ca", "#f5bde6", "#b7bdf8"]
EYES = ["#2d2f3d", "#40a02b", "#1e66f5", "#df8e1d"]


def cat_pixmap(seed, size=40):
    """Рисует мордочку кота; цвет и узор зависят от seed (id чата)."""
    rnd = random.Random(str(seed))
    fur = QColor(rnd.choice(FUR))
    shade = fur.darker(140)
    iris = QColor(rnd.choice(EYES))
    striped = rnd.random() < 0.6

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    def pt(x, y):
        return QPointF(x * size, y * size)

    def poly(*pts):
        return QPolygonF([pt(x, y) for x, y in pts])

    line = max(1.0, size * 0.035)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(fur)
    p.drawPolygon(poly((0.10, 0.52), (0.16, 0.06), (0.44, 0.28)))   # уши
    p.drawPolygon(poly((0.90, 0.52), (0.84, 0.06), (0.56, 0.28)))
    p.drawEllipse(pt(0.5, 0.60), 0.40 * size, 0.34 * size)           # голова
    p.setBrush(QColor("#f5bde6"))                                    # внутри ушей
    p.drawPolygon(poly((0.19, 0.40), (0.20, 0.17), (0.37, 0.30)))
    p.drawPolygon(poly((0.81, 0.40), (0.80, 0.17), (0.63, 0.30)))

    if striped:
        p.setPen(QPen(shade, line))
        for dx in (-0.08, 0.0, 0.08):
            p.drawLine(pt(0.5 + dx, 0.30), pt(0.5 + dx, 0.38))

    p.setPen(Qt.PenStyle.NoPen)
    for x in (0.36, 0.64):                                           # глаза
        p.setBrush(QColor("white"))
        p.drawEllipse(pt(x, 0.56), 0.075 * size, 0.085 * size)
        p.setBrush(iris)
        p.drawEllipse(pt(x, 0.57), 0.04 * size, 0.06 * size)
    p.setBrush(QColor("#ed8796"))                                    # нос
    p.drawPolygon(poly((0.46, 0.67), (0.54, 0.67), (0.5, 0.72)))

    p.setPen(QPen(shade, line))                                      # рот, усы
    p.drawLine(pt(0.5, 0.72), pt(0.45, 0.77))
    p.drawLine(pt(0.5, 0.72), pt(0.55, 0.77))
    for sx in (-1, 1):
        for dy in (-0.02, 0.03):
            p.drawLine(pt(0.5 + sx * 0.14, 0.70 + dy), pt(0.5 + sx * 0.36, 0.67 + dy * 2))
    p.end()
    return pm


def round_pixmap(src, size=72):
    """Обрезает картинку до круга size x size."""
    src = src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                     Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0.0, 0.0, float(size), float(size))
    p.setClipPath(path)
    p.drawPixmap((size - src.width()) // 2, (size - src.height()) // 2, src)
    p.end()
    return out


def pick_size(photo):
    """Самый большой вариант фото до PHOTO_PX (чтобы не качать оригинал)."""
    sizes = [x for x in photo.sizes if isinstance(x, types.PhotoSize)]
    if not sizes:
        sizes = [x for x in photo.sizes if hasattr(x, "w") and hasattr(x, "h")]
    if not sizes:
        return None
    small = [x for x in sizes if max(x.w, x.h) <= PHOTO_PX]
    if small:
        return max(small, key=lambda x: x.w * x.h)
    return min(sizes, key=lambda x: x.w * x.h)


def pick_thumb(doc):
    """Самое крупное превью документа (у анимированных стикеров это их статичный кадр)."""
    sizes = [x for x in (doc.thumbs or []) if isinstance(x, types.PhotoSize)]
    return max(sizes, key=lambda x: x.w * x.h) if sizes else None


_WEBP = None


def webp_ok():
    """Умеет ли эта сборка Qt читать WebP (в нём статичные стикеры и превью)."""
    global _WEBP
    if _WEBP is None:
        _WEBP = b"webp" in {bytes(f).lower() for f in QImageReader.supportedImageFormats()}
    return _WEBP


_WEBP_HELP = None


def webp_help():
    """Сможем ли показать WebP вообще: его читает Qt или есть внешний конвертер
    (dwebp / ffmpeg / ImageMagick / GraphicsMagick)."""
    global _WEBP_HELP
    if _WEBP_HELP is None:
        _WEBP_HELP = webp_ok() or any(
            shutil.which(x) for x in ("dwebp", "ffmpeg", "magick", "convert", "gm"))
    return _WEBP_HELP


def decode_image(data):
    """QImage из байтов. Если Qt не знает формат (например WebP — стикеры),
    пробует внешние конвертеры и переводит картинку в PNG.

    Возвращает пустую QImage, если не смог декодировать.
    """
    if not data:
        return QImage()
    img = QImage.fromData(data)
    if not img.isNull():
        return img
    fd, src = tempfile.mkstemp(suffix=".webp", prefix="catgram_")
    os.close(fd)
    out = src + ".png"
    try:
        Path(src).write_bytes(data)
        for cmd in (
            ["dwebp", "-quiet", src, "-o", out],
            ["ffmpeg", "-y", "-v", "error", "-i", src, "-frames:v", "1", out],
            ["magick", src, out],
            ["convert", src, out],
            ["gm", "convert", src, out],
        ):
            if not shutil.which(cmd[0]):
                continue
            try:
                subprocess.run(cmd, capture_output=True, timeout=15)
            except Exception:
                continue
            try:
                if os.path.getsize(out) > 0:
                    img = QImage(out)
                    if not img.isNull():
                        return img
            except OSError:
                pass
            try:   # этот конвертер не справился — чистим и пробуем следующий
                os.remove(out)
            except OSError:
                pass
    finally:
        for p in (src, out):
            try:
                os.remove(p)
            except OSError:
                pass
    return QImage()


def prepare_video(path):
    """Через ffprobe/ffmpeg (если установлены) узнаёт размеры и длительность видео и снимает кадр-превью.

    Возвращает (атрибуты для Telegram или None, путь к jpg-превью или None).
    Без ffmpeg видео всё равно отправится, только Telegram покажет его без превью.
    """
    attrs, thumb = None, None
    duration = 0
    if shutil.which("ffprobe"):
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_streams", "-show_format", "-of", "json", path],
                capture_output=True, timeout=20)
            data = json.loads(r.stdout)
            st = data["streams"][0]
            w, h = int(st["width"]), int(st["height"])
            rot = int(float(st.get("tags", {}).get("rotate", 0)))
            for sd in st.get("side_data_list", []):
                if "rotation" in sd:
                    rot = int(float(sd["rotation"]))
            if abs(rot) % 180 == 90:   # снято на телефон «лёжа» — размеры меняем местами
                w, h = h, w
            duration = float(data.get("format", {}).get("duration") or st.get("duration") or 0)
            attrs = types.DocumentAttributeVideo(
                duration=int(round(duration)), w=w, h=h, supports_streaming=True)
        except Exception:
            attrs = None
    if shutil.which("ffmpeg"):
        fd, out = tempfile.mkstemp(suffix=".jpg", prefix="catgram_")
        os.close(fd)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", "1" if duration > 2 else "0", "-i", path,
                 "-frames:v", "1", "-vf", "scale=320:320:force_original_aspect_ratio=decrease", out],
                capture_output=True, timeout=30)
            if os.path.getsize(out) > 0:
                thumb = out
        except Exception:
            pass
        if thumb is None:
            try:
                os.remove(out)
            except OSError:
                pass
    return attrs, thumb


class ChatView(QTextBrowser):
    """QTextBrowser, который отдаёт скачанные картинки по ссылкам catimg:...

    Пока фото ещё качается, вместо него отдаётся серая заглушка нужного размера
    (self.pending: ссылка -> (ширина, высота)), чтобы текст появлялся сразу.
    """

    def __init__(self, images):
        super().__init__()
        self.images = images
        self.pending = {}
        self.setOpenExternalLinks(True)

    def loadResource(self, rtype, name):
        key = name.toString()
        img = self.images.get(key)
        if img is not None:
            return img
        dims = self.pending.get(key)
        if dims:
            ph = QImage(dims[0], dims[1], QImage.Format.Format_RGB32)
            ph.fill(QColor(pal()["input"]))
            return ph
        return super().loadResource(rtype, name)


# ---------- настройки входа ----------

async def ask(title, label, password=False, integer=False):
    """Неблокирующий диалог ввода: возвращает значение или None при отмене.

    Модальный QInputDialog.getText() внутри корутины ломает asyncio-задачи
    Telethon (вложенный цикл событий), поэтому диалог показываем через show()
    и ждём результат через Future.
    """
    fut = asyncio.get_running_loop().create_future()
    dlg = QInputDialog()
    dlg.setWindowTitle(title)
    dlg.setLabelText(label)
    if integer:
        dlg.setInputMode(QInputDialog.InputMode.IntInput)
        dlg.setIntRange(0, 2**31 - 1)
    else:
        dlg.setInputMode(QInputDialog.InputMode.TextInput)
        if password:
            dlg.setTextEchoMode(QLineEdit.EchoMode.Password)

    def accepted():
        if not fut.done():
            if integer:
                fut.set_result(dlg.intValue())
            else:
                text = dlg.textValue()
                fut.set_result(text if password else text.strip())

    def rejected():
        if not fut.done():
            fut.set_result(None)

    dlg.accepted.connect(accepted)
    dlg.rejected.connect(rejected)
    dlg.show()
    try:
        return await fut
    finally:
        dlg.deleteLater()


async def get_credentials():
    """api_id / api_hash: из констант выше, переменных окружения, конфига или диалога."""
    if API_ID and API_HASH:
        return API_ID, API_HASH
    env_id, env_hash = os.environ.get("CATGRAM_API_ID"), os.environ.get("CATGRAM_API_HASH")
    if env_id and env_hash:
        return int(env_id), env_hash
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
        return int(cfg["api_id"]), cfg["api_hash"]
    except (OSError, ValueError, KeyError):
        pass

    api_id = await ask(tr("title"), tr("api_id"), integer=True)
    if not api_id:
        return None
    api_hash = await ask(tr("title"), tr("api_hash"))
    if not api_hash:
        return None

    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONFIG_FILE.write_text(json.dumps({"api_id": api_id, "api_hash": api_hash}))
    CONFIG_FILE.chmod(0o600)
    return api_id, api_hash


def normalize_phone(raw):
    """'+1 (202) 555-0123' -> '+12025550123'."""
    digits = "".join(c for c in raw if c.isdigit())
    return "+" + digits if digits else ""


async def login(client):
    await client.connect()
    if await client.is_user_authorized():
        return True
    title = tr("login")

    label = tr("phone")
    while True:
        raw = await ask(title, label)
        if not raw:
            return False
        phone = normalize_phone(raw)
        try:
            await client.send_code_request(phone)
            break
        except PhoneNumberInvalidError:
            label = tr("bad_phone")

    label = tr("code")
    while True:
        code = await ask(title, label)
        if not code:
            return False
        try:
            await client.sign_in(phone, code)
            return True
        except PhoneCodeInvalidError:
            label = tr("bad_code")
        except SessionPasswordNeededError:
            break

    label = tr("pw")
    while True:
        pw = await ask(title, label, password=True)
        if pw is None:
            return False
        try:
            await client.sign_in(password=pw)
            return True
        except PasswordHashInvalidError:
            label = tr("bad_pw")


# ---------- обновления ----------

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": f"catgram/{VERSION}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read(1_000_000))


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


# ---------- смайлики и мини-игры ----------

# Котики идут первыми — это же catgram. Клик по смайлику вставляет его в поле ввода.
EMOJIS = [
    "🐱", "😺", "😸", "😹", "😻", "😼", "😽", "🙀", "😿", "🐾",
    "😀", "😁", "😅", "😂", "🤣", "😉", "😊", "😍", "🥰", "😘",
    "😜", "🤪", "🥳", "😎", "🤩", "🤔", "🤨", "😐", "😴", "🤤",
    "🥺", "😳", "😢", "😭", "😤", "😠", "🤯", "😱", "🤗", "🤫",
    "🤭", "🫠", "🙃", "😇", "👀", "👻",
    "❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", "🤎", "💔",
    "💕", "💞", "💓", "💗", "💖", "💘", "💝", "💋",
    "👍", "👎", "👌", "✌️", "🤞", "🤙", "🫶", "🫡", "🙏", "🤝",
    "👋", "🫵", "🤲", "👏", "🙌", "💪", "🫂",
    "🐭", "🐹", "🐰", "🦊", "🐻", "🐼", "🐨", "🐯", "🦁", "🐮",
    "🐷", "🐸", "🐵", "🦄", "🐝", "🦋", "🐢", "🐙", "🦀", "🐠",
    "🍕", "🍔", "🍟", "🌭", "🍿", "🧁", "🍰", "🎂", "🍫", "🍩",
    "🍪", "🍭", "☕", "🍵", "🧋", "🍺", "🍷", "🥂", "🍾",
    "🔥", "✨", "⭐", "🌟", "💫", "🎉", "🎊", "🎁", "🎈", "💯",
    "🎮", "🎲", "🌸", "🌈", "☀️", "🌙", "⚡", "❄️", "💤", "💬",
]

MOVES = {   # стрелки и WASD — для обеих игр
    Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_A: (-1, 0),
    Qt.Key.Key_Right: (1, 0), Qt.Key.Key_D: (1, 0),
    Qt.Key.Key_Up: (0, -1), Qt.Key.Key_W: (0, -1),
    Qt.Key.Key_Down: (0, 1), Qt.Key.Key_S: (0, 1),
}


class SnakeGame(QWidget):
    """Котозмейка ловит мышей, пока собеседник печатает ответ.

    Управление: стрелки / WASD, пробел — пауза, R — начать заново.
    """

    CELL = 22
    COLS = 28
    ROWS = 18
    TOP = 34           # полоска сверху: счёт и подсказка
    TICK = 130         # мс между шагами

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(self.COLS * self.CELL, self.TOP + self.ROWS * self.CELL)
        self.best = S.get("best_snake", 0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)
        self.new_game()

    def new_game(self):
        cx, cy = self.COLS // 2, self.ROWS // 2
        self.snake = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]
        self.dir = (1, 0)
        self.next_dir = (1, 0)
        self.score = 0
        self.dead = False
        self.paused = False
        self.mouse = None
        self.place_mouse()
        self.timer.start(self.TICK)
        self.update()

    def place_mouse(self):
        free = [(x, y) for x in range(self.COLS) for y in range(self.ROWS)
                if (x, y) not in self.snake]
        self.mouse = random.choice(free) if free else None

    def hideEvent(self, e):
        self.paused = True          # таб скрыли — игра сама встаёт на паузу
        self.update()
        super().hideEvent(e)

    def keyPressEvent(self, e):
        if self.dead:
            if e.key() == Qt.Key.Key_R:
                self.new_game()
                e.accept()
            return
        d = MOVES.get(e.key())
        if d:
            if d[0] != -self.dir[0] or d[1] != -self.dir[1]:   # не разворачиваться на 180°
                self.next_dir = d
            self.paused = False    # любое движение снимает паузу
        elif e.key() == Qt.Key.Key_Space:
            self.paused = not self.paused
        elif e.key() == Qt.Key.Key_R:
            self.new_game()
        else:
            super().keyPressEvent(e)
            return
        self.update()
        e.accept()

    def step(self):
        if self.paused or self.dead:
            return
        self.dir = self.next_dir
        hx, hy = self.snake[0]
        nx, ny = hx + self.dir[0], hy + self.dir[1]
        if not (0 <= nx < self.COLS and 0 <= ny < self.ROWS) or (nx, ny) in self.snake[:-1]:
            self.dead = True
            self.timer.stop()
            self.update()
            return
        self.snake.insert(0, (nx, ny))
        if (nx, ny) == self.mouse:
            self.score += 1
            if self.score > self.best:       # рекорд пишем сразу
                self.best = self.score
                S["best_snake"] = self.best
                save_settings()
            self.place_mouse()
            self.timer.setInterval(max(60, self.TICK - 3 * self.score))   # чуть быстрее
        else:
            self.snake.pop()
        self.update()

    def paintEvent(self, _e):
        P = pal()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(P["panel"]))
        p.drawRect(self.rect())
        p.setBrush(QColor(P["bg"]))
        p.drawRoundedRect(QRectF(0, self.TOP, self.width(), self.height() - self.TOP), 8, 8)

        hud = p.font()
        hud.setPointSize(max(8, S["font_size"] - 2))
        p.setFont(hud)
        p.setPen(QColor(P["dim"]))
        p.drawText(QRectF(8, 4, self.width() / 2, self.TOP - 8),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f'{tr("score")}: {self.score}   {tr("best")}: {self.best}')
        p.drawText(QRectF(self.width() / 2, 4, self.width() / 2 - 8, self.TOP - 8),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   tr("game_hint"))

        def cell(x, y):
            return x * self.CELL, self.TOP + y * self.CELL, self.CELL, self.CELL

        if self.mouse is not None:   # мышь: серенькая, с розовыми ушками и хвостиком
            mx, my, mw, mh = cell(*self.mouse)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#a5adcb"))
            p.drawEllipse(QRectF(mx + mw * 0.2, my + mh * 0.28, mw * 0.6, mh * 0.48))
            p.setBrush(QColor("#ed8796"))
            p.drawEllipse(QRectF(mx + mw * 0.2, my + mh * 0.12, mw * 0.2, mh * 0.22))
            p.drawEllipse(QRectF(mx + mw * 0.6, my + mh * 0.12, mw * 0.2, mh * 0.22))
            p.setPen(QPen(QColor("#a5adcb"), 2))
            p.drawLine(int(mx + mw * 0.8), int(my + mh * 0.55),
                       int(mx + mw * 0.97), int(my + mh * 0.78))

        body, head = QColor(P["inn"]), QColor(P["out"])
        p.setPen(Qt.PenStyle.NoPen)
        for i, (x, y) in enumerate(self.snake):
            cx0, cy0, cw, ch = cell(x, y)
            p.setBrush(head if i == 0 else body)
            p.drawRoundedRect(QRectF(cx0 + 1, cy0 + 1, cw - 2, ch - 2), 6, 6)

        # мордочка на голове: ушки, глаза и усы
        hx, hy, hw, hh = cell(*self.snake[0])
        p.setBrush(head)
        for sx in (-1, 1):
            p.drawPolygon(QPolygonF([
                QPointF(hx + hw / 2 + sx * hw * 0.34, hy + 4),
                QPointF(hx + hw / 2 + sx * hw * 0.08, hy + 4),
                QPointF(hx + hw / 2 + sx * hw * 0.24, hy - hh * 0.06)]))
        dx, dy = self.dir
        ex = hx + hw * (0.5 + dx * 0.22)
        ey = hy + hh * (0.44 + dy * 0.18)
        px, py = -dy, dx
        for s in (-1, 1):
            p.setBrush(QColor("white"))
            p.drawEllipse(QRectF(ex + px * s * hw * 0.17 - hw * 0.07,
                                 ey + py * s * hh * 0.17 - hh * 0.09, hw * 0.14, hh * 0.18))
            p.setBrush(QColor("#2d2f3d"))
            p.drawEllipse(QRectF(ex + px * s * hw * 0.17 - hw * 0.035,
                                 ey + py * s * hh * 0.17 - hh * 0.045, hw * 0.07, hh * 0.09))
        p.setPen(QPen(QColor("#2d2f3d"), 1))
        for s in (-1, 1):
            p.drawLine(int(ex + px * s * hw * 0.3), int(ey + py * s * hh * 0.3),
                       int(ex + px * s * hw * 0.48), int(ey + py * s * hh * 0.24))

        if self.paused or self.dead:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(QRectF(0, self.TOP, self.width(), self.height() - self.TOP), 8, 8)
            big = p.font()
            big.setBold(True)
            big.setPointSize(max(10, S["font_size"]))
            p.setFont(big)
            p.setPen(QColor("white"))
            msg = tr("game_over") if self.dead else tr("paused")
            if self.dead:
                msg += f'\n{tr("score")}: {self.score}\n{tr("again")}'
            p.drawText(QRectF(0, self.TOP, self.width(), self.height() - self.TOP),
                       Qt.AlignmentFlag.AlignCenter, msg)
        p.end()


class Game2048(QWidget):
    """2048: собирай крупные плитки, пока в чате молчат.

    Управление: стрелки / WASD, R — начать заново.
    """

    N = 4
    CELL = 66
    GAP = 10
    TOP = 34
    TILE = {   # значение -> (цвет плитки, цвет цифры)
        2: ("#8aadf4", "#1e2030"), 4: ("#7dc4e8", "#1e2030"),
        8: ("#a6da95", "#1e2030"), 16: ("#eed49f", "#1e2030"),
        32: ("#f5a97f", "#1e2030"), 64: ("#ed8796", "#ffffff"),
        128: ("#c6a0f6", "#ffffff"), 256: ("#f5bde6", "#1e2030"),
        512: ("#8bd5ca", "#1e2030"), 1024: ("#ea76cb", "#ffffff"),
        2048: ("#df8e1d", "#ffffff"),
    }

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        side = self.N * self.CELL + (self.N + 1) * self.GAP
        self.setFixedSize(side, self.TOP + side)
        self.best = S.get("best_2048", 0)
        self.new_game()

    def new_game(self):
        self.board = [[0] * self.N for _ in range(self.N)]
        self.score = 0
        self.over = False
        self.spawn()
        self.spawn()
        self.update()

    def spawn(self):
        empty = [(y, x) for y in range(self.N) for x in range(self.N) if not self.board[y][x]]
        if empty:
            y, x = random.choice(empty)
            self.board[y][x] = 4 if random.random() < 0.1 else 2

    def keyPressEvent(self, e):
        if self.over:
            if e.key() == Qt.Key.Key_R:
                self.new_game()
                e.accept()
            return
        d = MOVES.get(e.key())
        if d:
            self.move(*d)
        elif e.key() == Qt.Key.Key_R:
            self.new_game()
        else:
            super().keyPressEvent(e)
            return
        e.accept()

    @staticmethod
    def slide(seq):
        """Сдвигает один ряд к его началу, склеивая одинаковые соседние плитки."""
        vals = [v for v in seq if v]
        out, i, gained = [], 0, 0
        while i < len(vals):
            if i + 1 < len(vals) and vals[i] == vals[i + 1]:
                out.append(vals[i] * 2)
                gained += vals[i] * 2
                i += 2
            else:
                out.append(vals[i])
                i += 1
        out += [0] * (len(seq) - len(out))
        return out, gained

    def move(self, dx, dy):
        before = [v for row in self.board for v in row]
        gained = 0
        for i in range(self.N):
            if dx:
                seq = [self.board[i][x] for x in range(self.N)]
                if dx > 0:
                    seq.reverse()
                line, g = self.slide(seq)
                gained += g
                if dx > 0:
                    line.reverse()
                for x in range(self.N):
                    self.board[i][x] = line[x]
            else:
                seq = [self.board[y][i] for y in range(self.N)]
                if dy > 0:
                    seq.reverse()
                line, g = self.slide(seq)
                gained += g
                if dy > 0:
                    line.reverse()
                for y in range(self.N):
                    self.board[y][i] = line[y]
        if [v for row in self.board for v in row] == before:
            return
        self.score += gained
        if self.score > self.best:      # рекорд пишем сразу
            self.best = self.score
            S["best_2048"] = self.best
            save_settings()
        self.spawn()
        if not self.can_move():
            self.over = True
        self.update()

    def can_move(self):
        for y in range(self.N):
            for x in range(self.N):
                v = self.board[y][x]
                if not v or (x + 1 < self.N and v == self.board[y][x + 1]) \
                        or (y + 1 < self.N and v == self.board[y + 1][x]):
                    return True
        return False

    def paintEvent(self, _e):
        P = pal()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(P["panel"]))
        p.drawRect(self.rect())

        hud = p.font()
        hud.setPointSize(max(8, S["font_size"] - 2))
        p.setFont(hud)
        p.setPen(QColor(P["dim"]))
        p.drawText(QRectF(8, 4, self.width() - 16, self.TOP - 8),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f'{tr("score")}: {self.score}   {tr("best")}: {self.best}')
        p.drawText(QRectF(8, 4, self.width() - 16, self.TOP - 8),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "R — ⟳")

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(P["bg"]))
        p.drawRoundedRect(QRectF(0, self.TOP, self.width(), self.height() - self.TOP), 8, 8)
        for y in range(self.N):
            for x in range(self.N):
                cx = self.GAP + x * (self.CELL + self.GAP)
                cy = self.TOP + self.GAP + y * (self.CELL + self.GAP)
                v = self.board[y][x]
                bg, fg = self.TILE.get(v, ("#e64553", "#ffffff"))
                p.setBrush(QColor(P["input"]) if not v else QColor(bg))
                p.drawRoundedRect(QRectF(cx, cy, self.CELL, self.CELL), 8, 8)
                if v:
                    tf = p.font()
                    tf.setBold(True)
                    tf.setPointSize(18 if v < 100 else 15 if v < 1000 else 12)
                    p.setFont(tf)
                    p.setPen(QColor(fg))
                    p.drawText(QRectF(cx, cy, self.CELL, self.CELL),
                               Qt.AlignmentFlag.AlignCenter, str(v))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setFont(hud)
        if self.over:
            p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(QRectF(0, self.TOP, self.width(), self.height() - self.TOP), 8, 8)
            big = p.font()
            big.setBold(True)
            big.setPointSize(max(10, S["font_size"]))
            p.setFont(big)
            p.setPen(QColor("white"))
            p.drawText(QRectF(0, self.TOP, self.width(), self.height() - self.TOP),
                       Qt.AlignmentFlag.AlignCenter,
                       f'{tr("game_over")}\n{tr("score")}: {self.score}\n{tr("again")}')
        p.end()


class StickerPanel(QDialog):
    """Панель стикеров: выбери набор сверху, клик по стикеру отправит его в открытый чат.

    Превью качаются в фоне (по четыре за раз) и остаются в кэше до конца работы catgram.
    """

    COLS = 6

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(tr("stickers"))
        self.setModal(False)
        self.resize(480, 540)
        self.sets = []          # наборы стикеров пользователя
        self.docs = {}          # id документа -> Document (по нему отправляем)
        self.thumbs = {}         # id документа -> QPixmap-превью
        self.sem = asyncio.Semaphore(4)   # не больше 4 превью одновременно
        self.set_epoch = 0      # выбор другого набора отменяет прошлую загрузку
        self.total = self.done = self.loaded = 0   # счётчики превью текущего набора
        self.first_error = None

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self.on_set)
        self.status = QLabel(tr("st_load"))
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        lay = QVBoxLayout(self)
        lay.addWidget(self.combo)
        lay.addWidget(self.status)
        lay.addWidget(self.scroll, 1)
        self.win.spawn(self.load_sets())

    async def load_sets(self):
        try:
            res = await self.win.client(functions.messages.GetAllStickersRequest(hash=0))
        except Exception:
            res = None
        self.sets = list(getattr(res, "sets", None) or [])
        if not self.sets:
            self.status.setText(tr("st_none"))
            return
        self.combo.currentIndexChanged.disconnect(self.on_set)   # addItem не дёргает загрузку
        for s in self.sets:
            self.combo.addItem(s.title or "?", s.id)
        self.combo.currentIndexChanged.connect(self.on_set)
        self.on_set(self.combo.currentIndex())

    def on_set(self, index):
        if 0 <= index < len(self.sets):
            self.win.spawn(self.load_set(index))

    async def load_set(self, index):
        s = self.sets[index]
        self.set_epoch += 1
        epoch = self.set_epoch
        self.status.show()
        self.status.setText(tr("st_load"))
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setSpacing(2)
        self.scroll.setWidget(inner)
        try:
            full = await self.win.client(functions.messages.GetStickerSetRequest(
                stickerset=types.InputStickerSetID(id=s.id, access_hash=s.access_hash),
                hash=0))
        except Exception as e:
            if epoch == self.set_epoch:
                self.status.setText(f"{tr('error')}: {e}")
            return
        if epoch != self.set_epoch:
            return   # уже выбрали другой набор
        docs = list(getattr(full, "documents", None) or [])
        emoji = {}   # id документа -> эмодзи пака
        for pack in getattr(full, "packs", None) or []:
            for did in pack.documents:
                emoji[did] = pack.emoticon
        row = col = 0
        self.total, self.done, self.loaded, self.first_error = len(docs), 0, 0, None
        for doc in docs:
            self.docs[doc.id] = doc
            b = QPushButton()
            b.setFixedSize(72, 72)
            b.setIconSize(QSize(64, 64))   # без этого Qt рисовал бы превью крошечным
            tip = emoji.get(doc.id, "")
            b.setToolTip(tip)
            if doc.id in self.thumbs:
                b.setIcon(QIcon(self.thumbs[doc.id]))
                self.done += 1
                self.loaded += 1
            else:
                b.setText(tip or "🐾")   # пока превью не скачалось
                self.win.spawn(self.fetch_thumb(doc, b, epoch))
            b.clicked.connect(lambda *_, d=doc: self.win.spawn(
                self.win.send_sticker(self.win.current, d)))
            grid.addWidget(b, row, col)
            col += 1
            if col >= self.COLS:
                col = 0
                row += 1
        if not docs:
            self.status.setText(tr("st_none"))
        else:
            self.tick()   # превью из кэша могли закрыть всю работу — обновить счётчик

    def tick(self):
        """Строка под списком наборов: сколько превью уже готово, или что случилось."""
        if self.done < self.total:
            self.status.show()
            self.status.setText(f"🐾 {self.done}/{self.total}")
        elif self.loaded:
            self.status.hide()
        else:
            self.status.show()
            if self.first_error:
                self.status.setText(f"{tr('error')}: {self.first_error}")
            elif not webp_help():
                self.status.setText(tr("st_webp"))
            else:
                self.status.setText(tr("st_fail"))

    async def fetch_thumb(self, doc, btn, epoch):
        data, err = None, None
        try:
            async with self.sem:
                thumb = pick_thumb(doc)
                try:
                    data = await self.win.client.download_media(doc, file=bytes, thumb=thumb)
                except Exception as e:
                    err = str(e)
                if not data and doc.size <= 400_000:
                    # запасной путь: маленький стикер (например статичный) качаем целиком
                    try:
                        data = await self.win.client.download_media(doc, file=bytes)
                    except Exception as e:
                        err = err or str(e)
        except Exception as e:
            err = err or str(e)
        if epoch != self.set_epoch:
            return   # выбрали другой набор — эта загрузка уже никому не нужна
        img = decode_image(data)
        if img.isNull():
            if self.first_error is None and err:
                self.first_error = err   # webp без поддержки Qt сюда не попадёт — он ниже
        else:
            pm = QPixmap.fromImage(img).scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self.thumbs[doc.id] = pm
            self.loaded += 1
            btn.setText("")
            btn.setIcon(QIcon(pm))
        self.done += 1
        self.tick()


# ---------- окно ----------

def media_tag(m):
    if m.sticker:
        return f'{tr("m_sticker")} {m.file.emoji or ""}'.strip()
    if m.photo:
        return tr("m_photo")
    if m.voice:
        return tr("m_voice")
    if m.video:
        return tr("m_video")
    if m.document:
        return tr("m_file")
    return tr("m_other") if m.media else ""


# ---------- звонки ----------
#
# Звонок 1:1 состоит из двух частей:
#   1. сигнализация — запрос, обмен ключами Диффи-Хеллмана, подтверждение, отбой;
#      её ведёт Telethon (запросы phone.* и обновления UpdatePhoneCall*);
#   2. голос и шифрование — библиотека ntgcalls (pip install ntgcalls).
# Без ntgcalls catgram работает как раньше, просто кнопка звонка покажет подсказку.

try:
    import ntgcalls
except Exception:   # не установлена или не подошла сборка
    ntgcalls = None

CALL_STALE = 90   # секунд: более старые «входящие» из очереди обновлений игнорируем
CALL_RATE = 48000   # частота дискретизации микрофона и динамиков
CALL_NTG_METHODS = ("create_p2p_call", "set_stream_sources", "init_exchange", "exchange_keys",
                    "connect_p2p", "send_signaling_data", "on_signaling_data",
                    "on_connection_change", "get_media_devices", "get_protocol",
                    "stop", "mute", "unmute")
CALL_NTG_NAMES = ("AudioDescription", "MediaDescription", "MediaSource", "StreamMode",
                  "DhConfig", "RTCServer")


async def _run(fn, *args):
    """Вызывает метод ntgcalls: в одних версиях он синхронный, в других — async."""
    res = fn(*args)
    return await res if inspect.isawaitable(res) else res


def audio_hints(devs, kind):
    """Разбирается, почему ntgcalls не видит звуковое устройство (kind: 'mic' | 'spk').

    На Linux ntgcalls перечисляет устройства через PulseAudio (подключаясь к уже
    работающему серверу, без его автозапуска) или, если libpulse не загрузилась,
    через ALSA. Пустой список — почти всегда одна из причин ниже; вместо сухого
    «не найдено» показываем подходящую подсказку. devs=None — список не получился.
    """
    import ctypes

    def _lib_loads():
        # проверяем так же, как это делает сам ntgcalls: dlopen по имени библиотеки
        # (ctypes.util.find_library сюда не годится — она может ошибочно вернуть None)
        for name in ("libpulse.so.0", "libasound.so.2"):
            try:
                ctypes.CDLL(name)
                return True
            except OSError:
                pass
        return False

    if devs is not None and (devs.microphone or devs.speaker):
        # что-то система всё-таки видит — не хватает конкретного устройства
        return tr("call_hint_mic" if kind == "mic" else "call_hint_spk")
    try:
        if not _lib_loads():
            return tr("call_hint_libs")   # ни libpulse, ни libasound — dlopen в ntgcalls пуст
        xdg = os.environ.get("XDG_RUNTIME_DIR") or ""
        if not (Path(xdg) / "pulse" / "native").exists() and not os.environ.get("PULSE_SERVER"):
            return tr("call_hint_server")   # сокет звукового сервера недоступен из этой сессии
    except Exception:
        pass   # сами проверки упали — покажем общий вариант ниже
    return tr("call_hint_pactl")   # странно: сервер есть, а устройств не видно


class CallDialog(QDialog):
    """Окно звонка: аватарка, имя, статус/таймер и кнопки. Логика — в Calls."""

    def __init__(self, win, did, name, incoming):
        super().__init__(win)
        self.setWindowTitle(tr("call_title"))
        self.setModal(False)
        self.setMinimumWidth(320)
        self.on_accept = self.on_hangup = self.on_mute = None   # их выставляет Calls
        self.over = False     # звонок закончен, закрытие окна больше не «кладёт трубку»
        self.muted = False
        self.t0 = None

        icon = win.icon_for(did)
        pic = QLabel()
        pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pic.setPixmap(icon.pixmap(QSize(120, 120)) if not icon.isNull()
                      else cat_pixmap(did, 120))
        who = QLabel(name)
        who.setTextFormat(Qt.TextFormat.PlainText)
        who.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = who.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 3)
        who.setFont(f)
        self.status = QLabel()
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)   # подсказки об ошибках бывают длинными

        self.accept_btn = QPushButton("✅ " + tr("call_accept"))
        self.accept_btn.clicked.connect(lambda *_: self.on_accept and self.on_accept())
        self.mute_btn = QPushButton("🎙 " + tr("call_mute"))
        self.mute_btn.clicked.connect(self.toggle_mute)
        self.hang_btn = QPushButton()
        self.hang_btn.clicked.connect(self.close)   # closeEvent и положит трубку

        row = QHBoxLayout()
        row.addWidget(self.accept_btn)
        row.addWidget(self.mute_btn)
        row.addWidget(self.hang_btn)
        lay = QVBoxLayout(self)
        lay.addWidget(pic)
        lay.addWidget(who)
        lay.addWidget(self.status)
        lay.addLayout(row)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.set_state("incoming" if incoming else "dialing")

    def set_state(self, state):
        """incoming | dialing | connecting | talking"""
        self.accept_btn.setVisible(state == "incoming")
        self.mute_btn.setVisible(state == "talking")
        self.hang_btn.setText("📵 " + tr("call_decline" if state == "incoming" else "call_end"))
        if state == "talking":
            self.t0 = time.monotonic()
            self.timer.start(1000)
            self.tick()
        else:
            self.status.setText(tr({"incoming": "call_incoming", "dialing": "call_dialing",
                                    "connecting": "call_connecting"}[state]))

    def tick(self):
        s = int(time.monotonic() - self.t0)
        self.status.setText(f"{tr('call_talking')} · {s // 60:02d}:{s % 60:02d}")

    def toggle_mute(self):
        self.muted = not self.muted
        self.mute_btn.setText(("🔇 " + tr("call_unmute")) if self.muted
                              else ("🎙 " + tr("call_mute")))
        if self.on_mute:
            self.on_mute(self.muted)

    def finish(self, text):
        """Звонок закончился: показываем итог и через пару секунд закрываем окно."""
        self.over = True
        self.timer.stop()
        self.status.setText(text)
        self.accept_btn.hide()
        self.mute_btn.hide()
        self.hang_btn.setEnabled(False)
        QTimer.singleShot(2000, self.close)

    def closeEvent(self, event):
        if not self.over:   # закрыли крестиком / нажали «Отклонить» посреди звонка
            self.over = True
            if self.on_hangup:
                self.on_hangup()
        event.accept()


class Calls:
    """Звонки 1:1: состояние текущего звонка, обработка обновлений Telegram, ntgcalls."""

    def __init__(self, win):
        self.win = win
        self.client = win.client
        self.ntg = None     # NTgCalls создаётся лениво, при первом звонке
        self.loop = None    # цикл asyncio — в него возвращаются колбэки из потоков ntgcalls
        self.call = None    # словарь с состоянием текущего звонка (или None)
        self.dlg = None

    def attach(self):
        self.client.add_event_handler(
            self.on_update,
            events.Raw((types.UpdatePhoneCall, types.UpdatePhoneCallSignalingData)))

    # --- ntgcalls ---

    def ensure_ntg(self):
        if ntgcalls is None:
            raise RuntimeError(tr("call_need_lib"))
        if self.ntg is None:
            ntg = ntgcalls.NTgCalls()
            # всё, что звонки 1:1 берут у ntgcalls; если чего-то нет — говорим прямо,
            # а не падаем на первом попавшемся AttributeError
            missing = [m for m in CALL_NTG_METHODS if not hasattr(ntg, m)]
            missing += ["ntgcalls." + n for n in CALL_NTG_NAMES if not hasattr(ntgcalls, n)]
            if missing:
                try:
                    from importlib.metadata import version
                    ver = version("ntgcalls")
                except Exception:
                    ver = "?"
                have = ", ".join(sorted(a for a in dir(ntg) if not a.startswith("_")))
                raise RuntimeError(tr("call_bad_lib").format(
                    ver=ver, missing=", ".join(missing), have=have))
            ntg.on_signaling_data(self._on_signaling)
            if hasattr(ntg, "on_connection_change"):
                ntg.on_connection_change(self._on_net)
            self.ntg = ntg
        return self.ntg

    async def media(self):
        """Что отправляем в линию: микрофон — первое устройство из списка системы.

        В ntgcalls 3.x медиа задаётся отдельно от create_p2p_call: сначала
        StreamMode.CAPTURE (наш звук), после connect_p2p — StreamMode.PLAYBACK.
        Если устройств не видно — не просто «не найдено», а причина и что чинить.
        """
        try:
            devs = await _run(self.ntg.get_media_devices)
        except Exception as e:
            raise RuntimeError(f"{tr('call_no_audio')}\n\n"
                               f"{tr('call_hint_throw').format(err=e)}\n"
                               f"{tr('call_hint_server')}") from e
        if not devs.microphone:
            raise RuntimeError(f"{tr('call_no_audio')}\n\n{audio_hints(devs, 'mic')}")
        return ntgcalls.MediaDescription(
            microphone=ntgcalls.AudioDescription(
                media_source=ntgcalls.MediaSource.DEVICE, input=devs.microphone[0].metadata,
                sample_rate=CALL_RATE, channel_count=1, keep_open=False),
            speaker=None, camera=None, screen=None)

    async def playback_media(self):
        """Где слушаем собеседника.

        Особенность ntgcalls: входящий звук выдаётся в слот microphone описания
        PLAYBACK (внутри это addTrack(Playback, Microphone)), поэтому туда
        попадает устройство динамиков — это не опечатка.
        """
        try:
            devs = await _run(self.ntg.get_media_devices)
        except Exception as e:
            raise RuntimeError(f"{tr('call_no_audio')}\n\n"
                               f"{tr('call_hint_throw').format(err=e)}\n"
                               f"{tr('call_hint_server')}") from e
        if not devs.speaker:
            raise RuntimeError(f"{tr('call_no_audio')}\n\n{audio_hints(devs, 'spk')}")
        return ntgcalls.MediaDescription(
            microphone=ntgcalls.AudioDescription(
                media_source=ntgcalls.MediaSource.DEVICE, input=devs.speaker[0].metadata,
                sample_rate=CALL_RATE, channel_count=1, keep_open=False),
            speaker=None, camera=None, screen=None)

    def protocol(self):
        p = self.ntg.get_protocol()
        return types.PhoneCallProtocol(
            min_layer=p.min_layer, max_layer=p.max_layer,
            library_versions=list(p.library_versions),
            udp_p2p=p.udp_p2p, udp_reflector=p.udp_reflector)

    @staticmethod
    def server(c):
        """PhoneConnection / PhoneConnectionWebrtc из Telegram → RTCServer для ntgcalls."""
        if hasattr(types, "PhoneConnectionWebrtc") and isinstance(c, types.PhoneConnectionWebrtc):
            return ntgcalls.RTCServer(c.id, c.ip, c.ipv6, c.port, c.username, c.password,
                                      c.turn, c.stun, False, None)
        # старый UDP-рефлектор: кредов нет, зато есть peer_tag
        return ntgcalls.RTCServer(c.id, c.ip, c.ipv6, c.port, None, None, True, False,
                                  bool(getattr(c, "tcp", False)), getattr(c, "peer_tag", None))

    async def dh_config(self):
        cfg = await self.client(functions.messages.GetDhConfigRequest(
            version=0, random_length=256))
        return ntgcalls.DhConfig(g=cfg.g, p=cfg.p, random=cfg.random)

    # колбэки ntgcalls приходят из его собственного потока — возвращаемся в цикл asyncio

    def _on_signaling(self, uid, data):
        if self.loop is not None:
            data = bytes(data)
            self.loop.call_soon_threadsafe(
                lambda: self.win.spawn(self.send_signaling(uid, data)))

    def _on_net(self, uid, info):
        st = getattr(info, "state", info)
        name = getattr(st, "name", None) or str(st).split(".")[-1]
        key = {"CONNECTED": "up", "FAILED": "down", "TIMEOUT": "down"}.get(name.upper())
        if key and self.loop is not None:
            self.loop.call_soon_threadsafe(self._net_changed, uid, key)

    def _net_changed(self, uid, key):
        c = self.call
        if not c or c["uid"] != uid:
            return
        if key == "up":
            self.set_talking(c)
        else:
            self.win.spawn(self.hangup(types.PhoneCallDiscardReasonDisconnect(),
                                       tr("call_failed")))

    def set_talking(self, c):
        if self.call is c and not c.get("started"):
            c["started"] = time.monotonic()
            if self.dlg:
                self.dlg.set_state("talking")

    async def send_signaling(self, uid, data):
        c = self.call
        if c and c["uid"] == uid and c["id"] is not None:
            try:
                await self.client(functions.phone.SendSignalingDataRequest(
                    peer=self.peer(c), data=data))
            except Exception as e:
                self.win.statusBar().showMessage(f"{tr('error')}: {e}", 8000)

    # --- вспомогательное ---

    @staticmethod
    def peer(c):
        return types.InputPhoneCall(id=c["id"], access_hash=c["hash"])

    def match(self, pc):
        """Состояние текущего звонка, если обновление относится к нему."""
        c = self.call
        if not c:
            return None
        if c["id"] is None and not c["incoming"] and \
                getattr(pc, "participant_id", None) == c["uid"]:
            c["id"], c["hash"] = pc.id, pc.access_hash   # обновление обогнало ответ сервера
        return c if c["id"] == pc.id else None

    async def name_of(self, uid):
        if uid in self.win.titles:
            return self.win.titles[uid]
        try:
            return get_display_name(await self.client.get_entity(uid)) or "?"
        except Exception:
            return "?"

    def open_dialog(self, uid, name, incoming):
        if self.dlg is not None:
            self.dlg.deleteLater()
        dlg = CallDialog(self.win, uid, name, incoming)
        dlg.on_accept = lambda: self.win.spawn(self.accept())
        dlg.on_hangup = lambda: self.win.spawn(self.hangup())
        dlg.on_mute = self.set_mute
        self.dlg = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        QApplication.alert(dlg, 0)   # мигнуть в панели задач, если окно не в фокусе

    def set_mute(self, muted):
        c = self.call
        if c and self.ntg is not None:
            self.win.spawn(_run(self.ntg.mute if muted else self.ntg.unmute, c["uid"]))

    # --- исходящий звонок ---

    async def start_call(self, uid):
        if self.call:
            self.win.statusBar().showMessage(tr("call_busy"), 5000)
            return
        try:
            self.ensure_ntg()
        except RuntimeError as e:
            self.win.notify(str(e))
            return
        self.loop = asyncio.get_running_loop()
        self.call = c = dict(uid=uid, incoming=False, id=None, hash=None)
        self.open_dialog(uid, await self.name_of(uid), incoming=False)
        try:
            user = await self.client.get_input_entity(uid)
            dh = await self.dh_config()
            await _run(self.ntg.create_p2p_call, uid)
            await _run(self.ntg.set_stream_sources, uid, ntgcalls.StreamMode.CAPTURE,
                      await self.media())
            g_a_hash = await _run(self.ntg.init_exchange, uid, dh, None)
            res = await self.client(functions.phone.RequestCallRequest(
                user_id=user, random_id=random.randint(0, 2 ** 31 - 1),
                g_a_hash=bytes(g_a_hash), protocol=self.protocol(), video=False))
            if self.call is c and c["id"] is None:
                c["id"], c["hash"] = res.phone_call.id, res.phone_call.access_hash
        except Exception as e:
            await self.fail(c, e)

    # --- входящий звонок: принять ---

    async def accept(self):
        c = self.call
        if not c or not c["incoming"] or c.get("accepted"):
            return
        c["accepted"] = True
        self.dlg.set_state("connecting")
        try:
            self.ensure_ntg()
            dh = await self.dh_config()
            await _run(self.ntg.create_p2p_call, c["uid"])
            await _run(self.ntg.set_stream_sources, c["uid"], ntgcalls.StreamMode.CAPTURE,
                       await self.media())
            g_b = await _run(self.ntg.init_exchange, c["uid"], dh, c["g_a_hash"])
            await self.client(functions.phone.AcceptCallRequest(
                peer=self.peer(c), g_b=bytes(g_b), protocol=self.protocol()))
        except Exception as e:
            await self.fail(c, e)

    # --- обновления от Telegram ---

    async def on_update(self, upd):
        if isinstance(upd, types.UpdatePhoneCallSignalingData):
            c = self.call
            if c and c["id"] == upd.phone_call_id and self.ntg is not None:
                data = bytes(upd.data)
                if c.get("connected"):
                    try:
                        await _run(self.ntg.send_signaling_data, c["uid"], data)
                    except Exception:
                        pass
                else:   # сигнализация может прийти раньше connect_p2p — держим очередь
                    c.setdefault("sig_in", []).append(data)
            return
        pc = upd.phone_call
        try:
            if isinstance(pc, types.PhoneCallRequested):
                await self.on_requested(pc)
            elif isinstance(pc, types.PhoneCallWaiting):
                self.match(pc)
            elif isinstance(pc, types.PhoneCallAccepted):
                await self.on_accepted(pc)
            elif isinstance(pc, types.PhoneCall):
                await self.on_ready(pc)
            elif isinstance(pc, types.PhoneCallDiscarded):
                await self.on_discarded(pc)
        except Exception as e:
            if self.call:
                await self.fail(self.call, e)
            else:
                self.win.statusBar().showMessage(f"{tr('error')}: {e}", 8000)

    async def on_requested(self, pc):
        """Нам звонят."""
        if time.time() - pc.date.timestamp() > CALL_STALE:
            return   # старое обновление из очереди — звонок давно закончился
        if self.call:
            await self.client(functions.phone.DiscardCallRequest(
                peer=types.InputPhoneCall(id=pc.id, access_hash=pc.access_hash),
                duration=0, reason=types.PhoneCallDiscardReasonBusy(), connection_id=0))
            return
        uid = pc.admin_id
        self.loop = asyncio.get_running_loop()
        self.call = dict(uid=uid, incoming=True, id=pc.id, hash=pc.access_hash,
                         g_a_hash=bytes(pc.g_a_hash))
        try:   # сообщаем звонящему, что у нас звонит
            await self.client(functions.phone.ReceivedCallRequest(peer=self.peer(self.call)))
        except Exception:
            pass
        self.open_dialog(uid, await self.name_of(uid), incoming=True)

    async def on_accepted(self, pc):
        """Собеседник принял наш звонок: достраиваем ключ и подтверждаем."""
        c = self.match(pc)
        if not c or c["incoming"] or c.get("confirmed"):
            return
        c["confirmed"] = True
        auth = await _run(self.ntg.exchange_keys, c["uid"], bytes(pc.g_b), 0)
        res = await self.client(functions.phone.ConfirmCallRequest(
            peer=self.peer(c), g_a=bytes(auth.g_a_or_b),
            key_fingerprint=auth.key_fingerprint, protocol=self.protocol()))
        await self.connect(c, res.phone_call)

    async def on_ready(self, pc):
        """Пришёл итоговый PhoneCall со списком серверов — можно соединяться."""
        c = self.match(pc)
        if not c:
            return
        if c["incoming"] and not c.get("keys"):
            if not c.get("accepted"):
                return
            # g_a должен совпасть с хешем, который звонящий прислал в самом начале
            if hashlib.sha256(bytes(pc.g_a_or_b)).digest() != c["g_a_hash"]:
                raise RuntimeError("g_a_hash mismatch")
            c["keys"] = True
            await _run(self.ntg.exchange_keys, c["uid"], bytes(pc.g_a_or_b),
                       pc.key_fingerprint)
        elif not c["incoming"] and not c.get("confirmed"):
            return
        await self.connect(c, pc)

    async def connect(self, c, pc):
        if c.get("connecting") or self.call is not c:
            return
        c["connecting"] = True
        self.dlg.set_state("connecting")
        await _run(self.ntg.connect_p2p, c["uid"], [self.server(x) for x in pc.connections],
                   list(pc.protocol.library_versions), bool(pc.p2p_allowed), None)
        # приём звука: отдельный источник PLAYBACK (входящий звук идёт в слот microphone)
        await _run(self.ntg.set_stream_sources, c["uid"], ntgcalls.StreamMode.PLAYBACK,
                   await self.playback_media())
        c["connected"] = True
        for data in c.pop("sig_in", []):   # сигнализация, пришедшая раньше соединения
            try:
                await _run(self.ntg.send_signaling_data, c["uid"], data)
            except Exception:
                pass
        if not hasattr(self.ntg, "on_connection_change"):   # некому сообщить «соединились»
            self.set_talking(c)

    async def on_discarded(self, pc):
        c = self.match(pc)
        if not c:
            return
        r = pc.reason
        if isinstance(r, types.PhoneCallDiscardReasonMissed):
            text = tr("call_missed")
        elif isinstance(r, types.PhoneCallDiscardReasonBusy):
            text = tr("call_peer_busy")
        elif isinstance(r, types.PhoneCallDiscardReasonDisconnect):
            text = tr("call_failed")
        else:
            text = tr("call_ended")
        await self.hangup(None, text, notify_server=False)

    # --- завершение ---

    def default_reason(self, c):
        if c["incoming"]:
            return (types.PhoneCallDiscardReasonHangup() if c.get("accepted")
                    else types.PhoneCallDiscardReasonBusy())
        return (types.PhoneCallDiscardReasonHangup() if c.get("confirmed")
                else types.PhoneCallDiscardReasonMissed())

    async def hangup(self, reason=None, text=None, notify_server=True):
        """Кладём трубку (или обрабатываем отбой с той стороны) и закрываем окно."""
        c, self.call = self.call, None
        if not c:
            return
        dlg, self.dlg = self.dlg, None
        if notify_server and c["id"] is not None:
            dur = int(time.monotonic() - c["started"]) if c.get("started") else 0
            try:
                await self.client(functions.phone.DiscardCallRequest(
                    peer=self.peer(c), duration=dur,
                    reason=reason or self.default_reason(c), connection_id=0))
            except Exception:
                pass
        if self.ntg is not None:
            try:
                await _run(self.ntg.stop, c["uid"])
            except Exception:
                pass   # create_p2p_call мог ещё не вызываться
        if dlg is not None:
            dlg.finish(text or tr("call_ended"))

    async def fail(self, c, err):
        if self.call is not c:
            return
        msg = f"{tr('error')}: {err}"
        self.win.statusBar().showMessage(msg.split("\n")[0], 8000)   # одна строка для бара
        await self.hangup(types.PhoneCallDiscardReasonDisconnect(), msg)


class CatGram(QMainWindow):
    def __init__(self, client, closing):
        super().__init__()
        self.client = client
        self.closing = closing
        self.current = None      # id открытого чата
        self.titles = {}         # id -> название
        self.unread = {}         # id -> непрочитанные
        self.items = {}          # id -> QListWidgetItem
        self.entities = {}       # id -> сущность Telethon (user/chat/channel)
        self.cat_icons = {}      # id -> QIcon с котом
        self.real_icons = {}     # id -> QIcon с настоящей аватаркой
        self.photo_cache = {}    # 'catimg:<чат>/<сообщение>' -> QImage
        self.dl_sem = asyncio.Semaphore(8)   # не больше 8 загрузок одновременно
        self.photo_jobs = set()  # ссылки фото, которые качаются прямо сейчас
        self.names = {}          # id отправителя -> имя (чтобы не ходить за ним по сети)
        self.online = {}         # id пользователя -> когда истекает статус «в сети» (unix-время)
        self.avatars_running = False
        self.shown = set()       # id сообщений, уже показанных в открытом чате
        self.searching = False   # в окне сообщений сейчас результаты поиска
        self.oldest_id = None    # id самого старого загруженного сообщения открытого чата
        self.history_done = False   # дошли до начала переписки
        self.paging = False      # подгрузка вверх разрешена (первая страница уже показана)
        self.older_busy = None   # «поколение», для которого сейчас идёт подгрузка вверх
        self.epoch = 0           # номер «поколения» окна: ответы для прошлого чата отбрасываются
        self._tasks = set()
        self.sticker_panel = None   # панель стикеров (создаётся лениво, переживает закрытия)
        self.calls = Calls(self)    # голосовые звонки

        self.setWindowIcon(QIcon(cat_pixmap("catgram", 128)))
        self.resize(1000, 650)

        # левая колонка: фильтр + список чатов
        self.chat_filter = QLineEdit()
        self.chat_filter.textChanged.connect(self.filter_chats)
        self.chats = QListWidget()
        self.chats.setMinimumWidth(260)
        self.chats.setIconSize(QSize(36, 36))
        self.chats.currentItemChanged.connect(self.on_chat_selected)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 0)
        ll.setSpacing(6)
        ll.addWidget(self.chat_filter)
        ll.addWidget(self.chats, 1)

        # правая колонка: поиск, сообщения / заглушка с котом, ввод
        self.msg_search = QLineEdit()
        self.msg_search.hide()
        self.msg_search.returnPressed.connect(self.on_search)

        self.header = QPushButton()          # шапка чата: аватарка + название, клик — инфо
        self.header.setObjectName("header")
        self.header.setFlat(True)
        self.header.setIconSize(QSize(32, 32))
        self.header.clicked.connect(self.open_info)
        self.header.hide()
        self.call_btn = QPushButton("📞")    # звонок в Telegram (через ntgcalls)
        self.call_btn.clicked.connect(self.on_call)
        self.call_btn.hide()
        self.tel_btn = QPushButton("📱")     # звонок на номер через системное приложение
        self.tel_btn.clicked.connect(self.on_call_tel)
        self.tel_btn.hide()
        head_row = QHBoxLayout()
        head_row.setSpacing(6)
        head_row.addWidget(self.header, 1)
        head_row.addWidget(self.call_btn)
        head_row.addWidget(self.tel_btn)

        self.view = ChatView(self.photo_cache)
        self.view.verticalScrollBar().valueChanged.connect(self.on_scroll)

        self.empty_cat = QLabel()
        self.empty_cat.setPixmap(cat_pixmap("empty", 160))
        self.empty_cat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_text = QLabel()
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.addStretch(1)
        el.addWidget(self.empty_cat)
        el.addWidget(self.empty_text)
        el.addStretch(1)

        self.stack = QStackedWidget()
        self.stack.addWidget(empty)      # 0 — чат не выбран
        self.stack.addWidget(self.view)  # 1 — сообщения

        self.input = QLineEdit()
        self.input.returnPressed.connect(self.on_send)
        self.attach = QPushButton("📎")
        self.attach.clicked.connect(self.on_attach)
        self.emoji_btn = QPushButton("😺")   # панель смайликов
        self.emoji_btn.clicked.connect(self.open_emoji)
        self.sticker_btn = QPushButton("🐾")   # панель стикеров
        self.sticker_btn.clicked.connect(self.open_stickers)
        send_row = QHBoxLayout()
        send_row.setSpacing(6)
        send_row.addWidget(self.attach)
        send_row.addWidget(self.emoji_btn)
        send_row.addWidget(self.sticker_btn)
        send_row.addWidget(self.input, 1)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 6, 6, 8)
        rl.addLayout(head_row)
        rl.addWidget(self.msg_search)
        rl.addWidget(self.stack, 1)
        rl.addLayout(send_row)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)

        # меню
        self.menu = self.menuBar().addMenu("")
        self.act_settings = QAction(self)
        self.act_settings.setShortcut(QKeySequence("Ctrl+,"))
        self.act_settings.triggered.connect(self.open_settings)
        self.act_search = QAction(self)
        self.act_search.setShortcut(QKeySequence("Ctrl+F"))
        self.act_search.triggered.connect(self.open_search)
        self.act_info = QAction(self)
        self.act_info.setShortcut(QKeySequence("Ctrl+I"))
        self.act_info.triggered.connect(self.open_info)
        self.act_call = QAction(self)
        self.act_call.setShortcut(QKeySequence("Ctrl+L"))
        self.act_call.triggered.connect(self.on_call)
        self.act_call_tel = QAction(self)
        self.act_call_tel.triggered.connect(self.on_call_tel)
        self.act_updates = QAction(self)
        self.act_updates.triggered.connect(lambda *_: self.spawn(self.check_updates(True)))
        self.act_games = QAction(self)          # мини-игры: скоротать ожидание ответа
        self.act_games.setShortcut(QKeySequence("Ctrl+G"))
        self.act_games.triggered.connect(self.open_games)
        self.act_quit = QAction(self)
        self.act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.act_quit.triggered.connect(lambda *_: self.close())
        for act in (self.act_info, self.act_search, self.act_call, self.act_call_tel,
                    self.act_settings, self.act_updates, self.act_games):
            self.menu.addAction(act)
        self.menu.addSeparator()
        self.menu.addAction(self.act_quit)
        QShortcut(QKeySequence("Escape"), self, activated=self.close_search)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.open_emoji)
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self.open_stickers)

        self.retranslate()

        # статус «в сети» истекает сам, если Telegram не прислал «был(а) в сети»
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.tick_status)
        self.status_timer.start(20000)

    # --- служебное ---

    def retranslate(self):
        self.setWindowTitle(tr("title"))
        self.menu.setTitle(tr("menu"))
        self.act_settings.setText(tr("settings"))
        self.act_search.setText(tr("search"))
        self.act_info.setText(tr("info"))
        self.act_call.setText(tr("call"))
        self.act_call_tel.setText(tr("call_tel"))
        self.act_updates.setText(tr("updates"))
        self.act_games.setText(tr("games"))
        self.act_quit.setText(tr("quit"))
        self.chat_filter.setPlaceholderText(tr("find_chats"))
        self.msg_search.setPlaceholderText(tr("find_msgs"))
        self.input.setPlaceholderText(tr("write"))
        self.attach.setToolTip(tr("attach_video"))
        self.emoji_btn.setToolTip(tr("emoji"))
        self.sticker_btn.setToolTip(tr("stickers"))
        if self.sticker_panel is not None:
            self.sticker_panel.setWindowTitle(tr("stickers"))
        self.empty_text.setText(tr("pick_chat"))

    def closeEvent(self, event):
        self.closing.set()
        event.accept()

    def spawn(self, coro):
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self._report)

    def _report(self, task):
        if not task.cancelled() and task.exception():
            self.statusBar().showMessage(f"{tr('error')}: {task.exception()}", 8000)

    def notify(self, text):
        """Неблокирующее окно с сообщением (ссылки кликабельны)."""
        box = QMessageBox(self)
        box.setWindowTitle(tr("title"))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(text)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.setModal(False)
        box.show()

    # --- чаты ---

    async def start(self):
        self.client.add_event_handler(self.on_new_message, events.NewMessage())
        self.client.add_event_handler(self.on_user_update, events.UserUpdate())
        self.calls.attach()
        async for d in self.client.iter_dialogs(limit=100):
            self.entities[d.id] = d.entity
            self.titles[d.id] = d.name or "?"
            self.unread[d.id] = d.unread_count
            self.note_status(d.id, d.entity)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, d.id)
            self.items[d.id] = item
            self.chats.addItem(item)
            self.refresh_item(d.id)
        self.apply_icons()
        if S["avatar_mode"] == "real":
            self.spawn(self.load_avatars())

    def refresh_item(self, did):
        n = self.unread.get(did, 0)
        title = self.titles.get(did, "?")
        if self.is_online(did):
            title += f"  ·  {tr('online')}"
        self.items[did].setText(f"{title}  ({n})" if n else title)

    def icon_for(self, did):
        mode = S["avatar_mode"]
        if mode == "none":
            return QIcon()
        if mode == "real" and did in self.real_icons:
            return self.real_icons[did]
        if did not in self.cat_icons:
            self.cat_icons[did] = QIcon(cat_pixmap(did, 72))
        return self.cat_icons[did]

    def apply_icons(self):
        for did, item in self.items.items():
            item.setIcon(self.icon_for(did))
        self.update_header()

    def note_status(self, uid, ent):
        if isinstance(ent, types.User) and isinstance(ent.status, types.UserStatusOnline):
            self.online[uid] = ent.status.expires.timestamp()
        else:
            self.online.pop(uid, None)

    def is_online(self, did):
        return self.online.get(did, 0) > time.time()

    def status_text(self, did):
        """«котится» / «не котится» для обычных людей; для групп, ботов и себя — пусто."""
        ent = self.entities.get(did)
        if not isinstance(ent, types.User) or ent.bot or ent.is_self or ent.deleted:
            return ""
        return tr("online" if self.is_online(did) else "offline")

    def tick_status(self):
        """Раз в несколько секунд: статус «в сети» мог истечь сам, без сообщения от Telegram."""
        for did in list(self.online):
            if did in self.items:
                self.refresh_item(did)
        self.update_header()

    async def on_user_update(self, event):
        status = getattr(event, "status", None)
        if status is None:   # «печатает» и прочее — нам нужны только смены статуса
            return
        uid = getattr(event, "user_id", None) or event.chat_id
        if isinstance(status, types.UserStatusOnline):
            self.online[uid] = status.expires.timestamp()
        else:
            self.online.pop(uid, None)
        if uid in self.items:
            self.refresh_item(uid)
        if uid == self.current:
            self.update_header()

    def can_call(self, did):
        """Звонить можно обычным людям — не ботам, не группам, не самому себе."""
        ent = self.entities.get(did)
        return isinstance(ent, types.User) and not (ent.bot or ent.is_self or ent.deleted)

    def phone_of(self, did):
        """Только цифры номера, если Telegram его показывает (настройки приватности)."""
        return re.sub(r"\D", "", getattr(self.entities.get(did), "phone", None) or "")

    def on_call(self, *_):
        if self.current is None:
            return
        if self.can_call(self.current):
            self.spawn(self.calls.start_call(self.current))
        else:
            self.statusBar().showMessage(tr("call_people_only"), 5000)

    def on_call_tel(self, *_):
        phone = self.phone_of(self.current) if self.current is not None else ""
        if not phone:
            self.statusBar().showMessage(tr("call_no_phone"), 6000)
        elif not QDesktopServices.openUrl(QUrl(f"tel:+{phone}")):
            self.notify(tr("call_tel_fail"))

    def update_header(self):
        if self.current is None:
            self.header.hide()
            self.call_btn.hide()
            self.tel_btn.hide()
            return
        ok = self.can_call(self.current)
        has_phone = ok and bool(self.phone_of(self.current))
        self.call_btn.setEnabled(ok)
        self.call_btn.setToolTip(tr("call" if ok else "call_people_only"))
        self.tel_btn.setEnabled(has_phone)
        self.tel_btn.setToolTip(tr("call_tel" if has_phone else "call_no_phone"))
        self.call_btn.show()
        self.tel_btn.show()
        title = self.titles.get(self.current, "?")
        status = self.status_text(self.current)
        if status:
            title += f"  ·  {status}"
        self.header.setText(title.replace("&", "&&"))
        self.header.setIcon(self.icon_for(self.current))
        self.header.show()

    async def avatar_bytes(self, did):
        """Аватарка из кэша на диске (до 7 дней) или с сервера; None — если фото нет."""
        path = AVATAR_DIR / f"{did}.jpg"
        try:
            if path.exists() and time.time() - path.stat().st_mtime < 7 * 86400:
                return path.read_bytes() or None
        except OSError:
            pass
        try:
            data = await self.client.download_profile_photo(self.entities[did], file=bytes)
        except Exception:
            return None
        try:
            AVATAR_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes(data or b"")   # пустой файл = «у чата нет фото»
        except OSError:
            pass
        return data or None

    async def load_avatars(self):
        if self.avatars_running:
            return
        self.avatars_running = True
        sem = asyncio.Semaphore(4)

        async def one(did):
            async with sem:
                data = await self.avatar_bytes(did)
            if not data:
                return
            pm = QPixmap()
            if not pm.loadFromData(data):
                return
            self.real_icons[did] = QIcon(round_pixmap(pm, 72))
            if S["avatar_mode"] == "real" and did in self.items:
                self.items[did].setIcon(self.real_icons[did])
                if did == self.current:
                    self.update_header()

        try:
            await asyncio.gather(*(one(d) for d in list(self.entities)), return_exceptions=True)
        finally:
            self.avatars_running = False

    def filter_chats(self, text):
        t = text.strip().lower()
        for did, item in self.items.items():
            item.setHidden(bool(t) and t not in self.titles[did].lower())

    # --- отрисовка ---

    async def name_of(self, m):
        sid = m.sender_id
        if sid in self.names:
            return self.names[sid]
        sender = m.sender or await m.get_sender()
        name = get_display_name(sender) if sender else "?"
        if sender and sid is not None:
            self.names[sid] = name
        return name

    def image_spec(self, m):
        """Что показать картинкой: (превью или None = сам файл, макс. ширина, (w, h)) либо None."""
        if m.photo:
            size = pick_size(m.photo)
            if size is not None:
                return size, 360, (size.w, size.h)
        elif m.sticker and webp_help():   # webp умеет Qt или подхватится конвертер
            if m.sticker.mime_type == "image/webp":          # статичный стикер — качаем целиком
                f = m.file
                return None, STICKER_PX, (f.width or 512, f.height or 512)
            thumb = pick_thumb(m.sticker)                    # анимированный / видео — берём кадр
            if thumb is not None:
                return thumb, STICKER_PX, (thumb.w, thumb.h)
        return None

    def flush_photos(self, todo):
        """Запускает фоновую закачку картинок в том порядке, в каком они лежат в todo."""
        for m, key, did, thumb, maxw in todo:
            if key not in self.photo_jobs:
                self.photo_jobs.add(key)
                self.spawn(self.fetch_photo(m, key, did, thumb, maxw))

    async def fetch_photo(self, m, key, did, thumb, maxw):
        """Скачивает картинку и подменяет серую заглушку в открытом окне."""
        try:
            async with self.dl_sem:
                if did != self.current:   # чат уже закрыли — не качаем зря
                    return
                data = await m.download_media(file=bytes, thumb=thumb)
            img = decode_image(data)
            if img.isNull():
                return
            if img.width() > maxw:
                img = img.scaledToWidth(maxw, Qt.TransformationMode.SmoothTransformation)
            self.photo_cache[key] = img
            while len(self.photo_cache) > 300:
                self.photo_cache.pop(next(iter(self.photo_cache)))
            if did == self.current:
                self.view.pending.pop(key, None)
                self.view.document().addResource(
                    QTextDocument.ResourceType.ImageResource.value, QUrl(key), img)
                self.view.viewport().update()
        except Exception:
            pass
        finally:
            self.photo_jobs.discard(key)

    async def render(self, m, with_date=False, todo=None):
        """HTML одного сообщения. Фото, которых ещё нет в кэше, попадают в todo."""
        if not m.message and not m.media:   # служебные сообщения пропускаем
            return ""
        P = pal()
        out = bool(m.out)
        who = tr("me") if out else await self.name_of(m)
        color = P["out"] if out else P["inn"]
        dt, now = m.date.astimezone(), datetime.now().astimezone()
        if dt.date() == now.date() and not with_date:
            fmt = "%H:%M"
        else:   # не сегодня — с датой; не этот год — ещё и с годом
            fmt = "%d.%m %H:%M" if dt.year == now.year else "%d.%m.%y %H:%M"
        when = dt.strftime(fmt)
        body = html.escape(m.message or "").replace("\n", "<br>")

        key, dims = None, ""
        spec = self.image_spec(m) if S["show_photos"] else None
        if spec:
            thumb, maxw, (sw, sh) = spec
            did = m.chat_id if m.chat_id is not None else self.current
            key = f"catimg:{did}/{m.id}"
            if key not in self.photo_cache:
                sw, sh = max(sw, 1), max(sh, 1)
                w = min(sw, maxw)
                h = max(1, round(sh * w / sw))
                self.view.pending[key] = (w, h)   # заглушка того же размера
                dims = f' width="{w}" height="{h}"'
                if todo is not None:
                    todo.append((m, key, did, thumb, maxw))
        tag = "" if key else media_tag(m)
        if tag:
            body = f"<i>{tag}</i> {body}".strip()
        if key:
            body = f'<img src="{key}"{dims}><br>{body}'
        return (f'<p style="margin:6px 0"><b style="color:{color}">{html.escape(who)}</b> '
                f'<span style="color:{P["dim"]}">{when}</span><br>{body}</p>')

    def scroll_down(self):
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    async def show_message(self, m):
        if self.searching or m.id in self.shown:
            return
        self.shown.add(m.id)
        todo = []
        chunk = await self.render(m, todo=todo)
        if chunk:
            self.view.append(chunk)
            self.scroll_down()
            self.flush_photos(todo)

    # --- действия ---

    def on_chat_selected(self, item, _prev):
        if item is None:
            return
        did = item.data(Qt.ItemDataRole.UserRole)
        self.current = did
        self.epoch += 1
        self.paging = False
        self.shown.clear()
        self.searching = False
        self.msg_search.clear()
        self.msg_search.hide()
        self.unread[did] = 0
        self.refresh_item(did)
        self.view.clear()
        self.stack.setCurrentIndex(1)
        self.update_header()
        self.spawn(self.load_history(did))

    async def load_history(self, did):
        self.epoch += 1
        epoch = self.epoch
        self.paging = False
        msgs = await self.client.get_messages(did, limit=PAGE)
        if did != self.current or self.searching or epoch != self.epoch:
            return   # уже переключились / идёт поиск / запущена более свежая загрузка
        parts, todo = [], []
        for m in reversed(msgs):
            self.shown.add(m.id)
            parts.append(await self.render(m, todo=todo))
        if did != self.current or self.searching or epoch != self.epoch:
            return
        self.oldest_id = msgs[-1].id if msgs else None
        self.history_done = len(msgs) < PAGE
        if self.history_done:
            parts.insert(0, self.start_marker())
        self.view.setHtml("".join(parts))
        self.scroll_down()
        self.flush_photos(todo[::-1])   # фото качаем с самых свежих — их видно первыми
        self.paging = True
        self.on_scroll(self.view.verticalScrollBar().value())   # короткий чат — сразу догрузить
        await self.client.send_read_acknowledge(did)

    # --- подгрузка старых сообщений при прокрутке вверх ---

    def start_marker(self):
        return (f'<p align="center" style="color:{pal()["dim"]}; margin:10px 0">'
                f'{html.escape(tr("hist_start"))}</p>')

    def near_top(self):
        bar = self.view.verticalScrollBar()
        return bar.value() < max(60, bar.pageStep())   # до верха меньше экрана

    def on_scroll(self, value):
        if self.near_top():   # подгружаем заранее, не дожидаясь самого верха
            self.want_older()

    def want_older(self):
        if (self.paging and not self.history_done and not self.searching
                and self.current is not None and self.older_busy != self.epoch):
            self.older_busy = self.epoch
            self.spawn(self.load_older(self.current))

    async def load_older(self, did):
        epoch = self.epoch
        self.statusBar().showMessage(tr("hist_loading"))
        try:
            while True:
                msgs = await self.client.get_messages(did, limit=PAGE_OLD, offset_id=self.oldest_id)
                if epoch != self.epoch or self.searching:
                    return
                parts, todo = [], []
                for m in reversed(msgs):
                    self.shown.add(m.id)
                    parts.append(await self.render(m, todo=todo))
                if epoch != self.epoch or self.searching:
                    return
                if msgs:
                    self.oldest_id = msgs[-1].id
                self.history_done = len(msgs) < PAGE_OLD
                if self.history_done:
                    parts.insert(0, self.start_marker())
                self.prepend_html("".join(parts))
                self.flush_photos(todo[::-1])
                # если контента всё ещё не хватает на прокрутку — тянем следующую страницу
                if self.history_done or not self.near_top():
                    return
        finally:
            if self.older_busy == epoch:
                self.older_busy = None
            self.statusBar().clearMessage()

    def prepend_html(self, markup):
        """Вставляет HTML в начало окна сообщений, не сдвигая то, что сейчас читает человек."""
        if not markup:
            return
        doc = self.view.document()
        bar = self.view.verticalScrollBar()
        anchor = QTextCursor(doc.begin())    # стоит на первом из уже показанных сообщений
        y0 = self.view.cursorRect(anchor).top()
        cur = QTextCursor(doc)
        cur.movePosition(QTextCursor.MoveOperation.Start)
        cur.insertHtml(markup)
        if not cur.atBlockStart():           # хвост вставки мог слиться с первым абзацем
            cur.insertBlock()
        doc.size()                           # досчитать раскладку, иначе диапазон прокрутки неточен
        bar.setValue(bar.value() + self.view.cursorRect(anchor).top() - y0)

    def on_send(self):
        text = self.input.text().strip()
        if not text or self.current is None:
            return
        self.input.clear()
        self.spawn(self.send(self.current, text))

    async def send(self, did, text):
        m = await self.client.send_message(did, text)
        if did == self.current:
            await self.show_message(m)

    def on_attach(self, *_):
        if self.current is None:
            return
        flt = (f"{tr('video_files')} (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.3gp);;"
               f"{tr('all_files')} (*)")
        path, _flt = QFileDialog.getOpenFileName(self, tr("pick_video"), str(Path.home()), flt)
        if not path:
            return
        caption = self.input.text().strip()   # что написано в поле — станет подписью к видео
        self.input.clear()
        self.spawn(self.send_video(self.current, path, caption))

    async def send_video(self, did, path, caption):
        name = os.path.basename(path)
        thumb = None
        self.attach.setEnabled(False)   # пока одно видео уходит, второе не запускаем
        try:
            self.statusBar().showMessage(f"{tr('sending_video')}: {name}…")
            attrs, thumb = await asyncio.to_thread(prepare_video, path)

            def progress(sent, total):
                pct = int(sent * 100 / total) if total else 0
                self.statusBar().showMessage(f"{tr('sending_video')}: {name} — {pct}%")

            m = await self.client.send_file(
                did, path, caption=caption or None, supports_streaming=True,
                attributes=[attrs] if attrs else None, thumb=thumb,
                progress_callback=progress)
            if did == self.current:
                await self.show_message(m)
        finally:
            self.attach.setEnabled(True)
            self.statusBar().clearMessage()
            if thumb:
                try:
                    os.remove(thumb)
                except OSError:
                    pass

    # --- игры и смайлики ---

    def open_games(self, *_):
        """Мини-игры, пока собеседник молчит и печатает ответ."""
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("games"))
        dlg.setModal(False)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        tabs = QTabWidget()
        tabs.addTab(SnakeGame(), tr("snake"))
        tabs.addTab(Game2048(), tr("g2048"))
        hint = QLabel(tr("wait_hint"))
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay = QVBoxLayout(dlg)
        lay.addWidget(tabs)
        lay.addWidget(hint)
        dlg.show()

    def open_emoji(self, *_):
        """Панель смайликов: клик вставляет эмодзи в поле ввода, окно остаётся открытым."""
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("emoji"))
        dlg.setModal(False)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        grid = QGridLayout()
        grid.setSpacing(2)
        for i, ch in enumerate(EMOJIS):
            b = QPushButton(ch)
            b.setFixedSize(38, 34)
            f = b.font()
            f.setPointSize(13)
            b.setFont(f)
            b.clicked.connect(lambda *_, ch=ch: self.insert_emoji(ch))
            grid.addWidget(b, i // 8, i % 8)
        inner = QWidget()
        inner.setLayout(grid)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(420)
        lay = QVBoxLayout(dlg)
        lay.addWidget(scroll)
        dlg.show()

    def insert_emoji(self, ch):
        self.input.insert(ch)   # вставляется там, где курсор в поле ввода

    def open_stickers(self, *_):
        """Панель стикеров: клик по стикеру отправляет его в открытый чат."""
        if self.current is None:
            return
        if self.sticker_panel is None:
            self.sticker_panel = StickerPanel(self)
        self.sticker_panel.show()
        self.sticker_panel.raise_()
        self.sticker_panel.activateWindow()

    async def send_sticker(self, did, doc):
        if did is None:
            return
        m = await self.client.send_file(did, doc)
        if did == self.current:
            await self.show_message(m)

    async def on_new_message(self, event):
        did = event.chat_id
        if did == self.current:
            await self.show_message(event.message)
            if not self.searching:
                await self.client.send_read_acknowledge(did, event.message)
        elif did in self.items and not event.message.out:
            self.unread[did] = self.unread.get(did, 0) + 1
            self.refresh_item(did)

    # --- поиск по сообщениям ---

    def open_search(self, *_):
        if self.current is None:
            return
        self.msg_search.show()
        self.msg_search.setFocus()
        self.msg_search.selectAll()

    def close_search(self, *_):
        if not self.msg_search.isVisible():
            return
        self.msg_search.clear()
        self.msg_search.hide()
        self.searching = False
        self.paging = False
        if self.current is not None:
            self.shown.clear()
            self.spawn(self.load_history(self.current))

    def on_search(self):
        query = self.msg_search.text().strip()
        if self.current is None:
            return
        self.paging = False   # окно сейчас займёт поиск или перезагрузка истории
        if not query:
            self.searching = False
            self.shown.clear()
            self.spawn(self.load_history(self.current))
            return
        self.searching = True
        self.spawn(self.search_messages(self.current, query))

    async def search_messages(self, did, query):
        msgs = [m async for m in self.client.iter_messages(did, search=query, limit=50)]
        todo = []
        parts = [await self.render(m, with_date=True, todo=todo) for m in msgs]
        parts = [p for p in parts if p]
        if did != self.current or not self.searching:
            return
        dim = pal()["dim"]
        head = (f'<p style="color:{dim}">🔍 {tr("res")}: {html.escape(query)} — '
                f'{len(parts) or tr("nothing")}</p>')
        self.view.setHtml(head + "".join(parts))
        self.view.verticalScrollBar().setValue(0)
        self.flush_photos(todo)

    # --- информация о чате / профиле ---

    def open_info(self, *_):
        if self.current is not None:
            self.spawn(self.show_info(self.current))

    async def show_info(self, did):
        ent = self.entities.get(did)
        if ent is None:
            return
        about, members = "", None
        try:
            if isinstance(ent, types.User):
                full = await self.client(functions.users.GetFullUserRequest(ent))
                about = full.full_user.about or ""
            elif isinstance(ent, types.Channel):
                full = await self.client(functions.channels.GetFullChannelRequest(ent))
                about = full.full_chat.about or ""
                members = getattr(full.full_chat, "participants_count", None)
            elif isinstance(ent, types.Chat):
                full = await self.client(functions.messages.GetFullChatRequest(ent.id))
                about = full.full_chat.about or ""
                parts = getattr(full.full_chat, "participants", None)
                members = len(getattr(parts, "participants", None) or []) or None
        except Exception as e:
            self.statusBar().showMessage(f"{tr('error')}: {e}", 8000)
        try:
            big = await self.client.download_profile_photo(ent, file=bytes, download_big=True)
        except Exception:
            big = None

        title = self.titles.get(did, "?")
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg)

        pic = QLabel()
        pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = QPixmap()
        if big and pm.loadFromData(big):
            pic.setPixmap(round_pixmap(pm, 200))
        else:
            pic.setPixmap(cat_pixmap(did, 160))
        lay.addWidget(pic)

        def label(text, bold=False, center=False):
            lab = QLabel(text)
            lab.setTextFormat(Qt.TextFormat.PlainText)
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if bold:
                f = lab.font()
                f.setBold(True)
                lab.setFont(f)
            if center:
                lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return lab

        lay.addWidget(label(title, bold=True, center=True))
        lines = []
        username = getattr(ent, "username", None)
        if username:
            lines.append(f"{tr('username')}: @{username}")
        phone = getattr(ent, "phone", None)
        if phone:
            lines.append(f"{tr('phone_lbl')}: +{phone}")
        if members:
            lines.append(f"{tr('members')}: {members}")
        if lines:
            lay.addWidget(label("\n".join(lines)))
        if about:
            lay.addWidget(label(tr("about"), bold=True))
            lay.addWidget(label(about))
        dlg.show()

    # --- настройки ---

    def open_settings(self, *_):
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("set_title"))
        form = QFormLayout(dlg)

        lang = QComboBox()
        for code, name in LANGS.items():
            lang.addItem(name, code)
        lang.setCurrentIndex(lang.findData(S["lang"]))
        theme = QComboBox()
        theme.addItem(tr("theme_dark"), "dark")
        theme.addItem(tr("theme_light"), "light")
        theme.setCurrentIndex(theme.findData(S["theme"]))
        size = QSpinBox()
        size.setRange(10, 24)
        size.setValue(S["font_size"])
        avatars = QComboBox()
        avatars.addItem(tr("av_real"), "real")
        avatars.addItem(tr("av_cats"), "cats")
        avatars.addItem(tr("av_none"), "none")
        avatars.setCurrentIndex(avatars.findData(S["avatar_mode"]))
        photos = QCheckBox()
        photos.setChecked(S["show_photos"])
        upd = QCheckBox()
        upd.setChecked(S["check_updates"])
        url = QLineEdit(S["update_url"])
        url.setPlaceholderText("https://api.github.com/repos/<user>/catgram/releases/latest")
        url.setMinimumWidth(360)

        form.addRow(tr("set_lang"), lang)
        form.addRow(tr("set_theme"), theme)
        form.addRow(tr("set_font"), size)
        form.addRow(tr("set_avatars"), avatars)
        form.addRow(tr("set_photos"), photos)
        form.addRow(tr("set_upd_start"), upd)
        form.addRow(tr("set_upd_url"), url)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                               QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)

        if not dlg.exec():
            return
        S.update(lang=lang.currentData(), theme=theme.currentData(),
                 font_size=size.value(), avatar_mode=avatars.currentData(),
                 show_photos=photos.isChecked(),
                 check_updates=upd.isChecked(), update_url=url.text().strip())
        save_settings()
        self.apply_settings()

    def apply_settings(self):
        QApplication.instance().setStyleSheet(make_style())
        self.retranslate()
        if S["avatar_mode"] == "real":
            self.spawn(self.load_avatars())
        self.apply_icons()
        if self.current is not None and not self.searching:
            self.shown.clear()
            self.spawn(self.load_history(self.current))

    # --- обновления ---

    async def check_updates(self, manual=False):
        url = S["update_url"]
        if not url.lower().startswith("https://"):
            if manual:
                self.notify(tr("upd_no_url"))
            return
        try:
            data = await asyncio.to_thread(fetch_json, url)
            latest = str(data.get("tag_name") or data.get("version") or "")
            link = str(data.get("html_url") or data.get("url") or url)
        except Exception as e:
            if manual:
                self.notify(f'{tr("upd_err")}: {html.escape(str(e))}')
            return
        if not link.lower().startswith("https://"):
            link = url
        if version_tuple(latest) > version_tuple(VERSION):
            self.notify(f'{tr("upd_new")}: <b>{html.escape(latest)}</b> (v{VERSION})<br>'
                        f'<a href="{html.escape(link)}">{html.escape(link)}</a>')
        elif manual:
            self.notify(tr("upd_latest"))


# ---------- запуск ----------

async def amain(closing):
    creds = await get_credentials()
    if not creds:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    client = TelegramClient(str(DATA_DIR / APP), *creds)
    try:
        if not await login(client):
            return
        # файл сессии = доступ к аккаунту, держим его приватным
        for f in DATA_DIR.glob(f"{APP}.session*"):
            f.chmod(0o600)
        win = CatGram(client, closing)
        win.show()
        await win.start()
        if S["check_updates"]:
            win.spawn(win.check_updates())
        await closing.wait()
        try:   # не оставляем звонок висеть, если окно закрыли посреди разговора
            await asyncio.wait_for(win.calls.hangup(), 3)
        except Exception:
            pass
    finally:
        await client.disconnect()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setWindowIcon(QIcon(cat_pixmap("catgram", 128)))
    app.setStyleSheet(make_style())
    # не выходим, когда закрылся последний диалог входа; выход — по закрытию главного окна
    app.setQuitOnLastWindowClosed(False)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    closing = asyncio.Event()
    with loop:
        loop.run_until_complete(amain(closing))


if __name__ == "__main__":
    main()
