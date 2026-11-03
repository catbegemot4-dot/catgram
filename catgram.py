#!/usr/bin/env python3
"""catgram — маленький клиент Telegram для Linux (PyQt6 + Telethon)."""
import asyncio
import html
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
from PyQt6.QtCore import QPointF, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QAction, QColor, QIcon, QImage, QImageReader, QKeySequence, QPainter, QPainterPath, QPen,
    QPixmap,
    QPolygonF, QShortcut, QTextCursor, QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QSplitter, QStackedWidget, QTextBrowser,
    QVBoxLayout, QWidget,
)
from telethon import TelegramClient, events, functions, types
from telethon.errors import (
    PasswordHashInvalidError, PhoneCodeInvalidError, PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.utils import get_display_name

APP = "catgram"
VERSION = "0.3.0"
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
        send_row = QHBoxLayout()
        send_row.setSpacing(6)
        send_row.addWidget(self.attach)
        send_row.addWidget(self.input, 1)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 6, 6, 8)
        rl.addWidget(self.header)
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
        self.act_updates = QAction(self)
        self.act_updates.triggered.connect(lambda *_: self.spawn(self.check_updates(True)))
        self.act_quit = QAction(self)
        self.act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.act_quit.triggered.connect(lambda *_: self.close())
        for act in (self.act_info, self.act_search, self.act_settings, self.act_updates):
            self.menu.addAction(act)
        self.menu.addSeparator()
        self.menu.addAction(self.act_quit)
        QShortcut(QKeySequence("Escape"), self, activated=self.close_search)

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
        self.act_updates.setText(tr("updates"))
        self.act_quit.setText(tr("quit"))
        self.chat_filter.setPlaceholderText(tr("find_chats"))
        self.msg_search.setPlaceholderText(tr("find_msgs"))
        self.input.setPlaceholderText(tr("write"))
        self.attach.setToolTip(tr("attach_video"))
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

    def update_header(self):
        if self.current is None:
            self.header.hide()
            return
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
        elif m.sticker and webp_ok():
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
            img = QImage.fromData(data) if data else QImage()
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
