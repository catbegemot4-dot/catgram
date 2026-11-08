#!/usr/bin/env python3
"""catgram — маленький клиент Telegram для Linux (PyQt6 + Telethon)."""
import asyncio
import glob
import hashlib
import html
import inspect
import json
import math
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path
from string import Template

import qasync
from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QAction, QColor, QCursor, QDesktopServices, QIcon, QImage, QImageReader, QKeySequence,
    QPainter, QPainterPath, QPen, QPixmap,
    QPolygonF, QShortcut, QTextCursor, QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGridLayout, QHBoxLayout, QGraphicsScene, QGraphicsView, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox,
    QSplitter,
    QStackedWidget, QSystemTrayIcon, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)
try:   # встроенный видеоплеер — если установлен QtMultimedia
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoWidget
    MULTIMEDIA = True
except Exception:   # нет модуля — видео откроет системный плеер
    MULTIMEDIA = False

# О библиотеке MTProto: Telethon остаётся нарочно — это самая быстрая
# поддерживаемая библиотека Telegram-API для Python (pyrogram заброшен
# с 2020-го, форки живут на патчах). «Ускорение» сделано настройками:
# поднят порог ожидания flood-wait, медиа качается параллельно
# (dl_sem), имена и аватарки кэшируются — лишних сетевых ходов нет.
from telethon import TelegramClient, events, functions, types
from telethon.errors import (
    PasswordHashInvalidError, PhoneCodeInvalidError, PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.utils import get_display_name

APP = "catgram"
VERSION = "0.9.13"
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


# ---------- архитектура ----------
#
# catgram повторяет разбивку на слои официального Telegram Desktop
# (клиент под GPLv3; его код мы не копировали — взяли только архитектуру
# и набор компонентов, реализация здесь своя, на PyQt6 + Telethon):
#
#   * core-слой   — настройки, языки, палитры, QSS (секции ниже:
#                   «языки», «настройки», «тема»);
#   * data-слой   — Telethon: сессии, диалоги, сообщения, медиа;
#   * ui-слой     — компоненты-виджеты:
#                   - ChatView    ~ HistoryWidget: окно переписки;
#                   - PhotoViewer ~ Media::View: полноэкранный оверлей
#                     просмотра фото с зумом и листанием;
#                   - info-панель ~ третья колонка профиля собеседника
#                     (UserProfile в правой колонке Telegram Desktop);
#                   - контекстное меню сообщения (копировать / ответить /
#                     переслать / закрепить / удалить);
#                   - разделители дней в истории (группировка по дате);
#   * main-слой   — CatGram(QMainWindow): три колонки основного окна —
#                   список диалогов, история, панель профиля.
#
# Список диалогов и вся навигация уже жили в CatGram; в этой версии
# добавлены перечисленные выше компоненты Telegram Desktop.


# ---------- языки ----------

LANGS = {"ru": "Русский", "en": "English", "uk": "Українська",
         "es": "Español", "fr": "Français", "de": "Deutsch", "it": "Italiano",
         "pt": "Português", "pl": "Polski", "tr": "Türkçe", "zh": "中文",
         "ja": "日本語", "ar": "العربية"}

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
        "set_noise": "Noise suppression in calls",
        "set_wallpaper": "Chat wallpaper", "wp_none": "None", "wp_paws": "Cat paws 🐾",
        "wp_stars": "Stars ✨",
        "noise_off": "Noise suppression unavailable",
        "noise_on": "Noise suppression: {name}", "test_noise": "Test",
        "accounts": "Accounts…", "acc_add": "Add account",
        "acc_switch": "Switch", "acc_remove": "Remove",
        "acc_del_q": "Remove account {name}?",
        "acc_switch_q": "Restart catgram and switch to {name}?",
        "acc_limit": "Limit reached: 100 additional accounts",
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
        "tetris": "🧱 Catetris", "lines": "Lines",
        "tetris_hint": "←→↓ — move · ↑ — rotate · Space — drop · P — pause",
        "mines": "💣 Minesweeper",
        "mines_hint": "LMB — open · RMB — flag · R — new game",
        "win": "You win!", "lose": "You lose", "draw": "Draw",
        "cards": "🃏 War", "card_ranks": "6 7 8 9 10 J Q K A",
        "cards_you": "You", "cards_cat": "Cat",
        "cards_move": "Click or Space — next round",
        "cards_war": "⚔️ War! Cards stay on the table",
        "mario": "🐱 Super Cat", "lives": "Lives", "coins": "Coins",
        "mario_hint": "←→ — run · ↑ / Space — jump · stomp the mice!",
        "kart": "🏎 Cat Kart", "lap": "Lap", "place": "Place",
        "kart_hint": "↑ — gas · ←→ — steer · ↓ — brake",
        "arka": "🧱 Catanoid",
        "arka_hint": "Mouse / ←→ — paddle · don't drop the ball",
        "g15": "🧩 15 puzzle", "moves": "Moves", "solved": "Solved!",
        "pairs": "🎴 Find pairs",
        "xo": "⭕ Tic-tac-toe", "xo_you": "Your turn", "xo_cat": "Cat's turn",
        "chess": "♞ Chess", "checkers": "Checkers", "turn_white": "White's turn",
        "tanks": "▮ Tanks", "gsearch": "Global search", "media_search": "Chat media",
        "translate_chat": "Translate chat", "translating": "Translating…",
        "gs_hint": "Search all chats and messages",
        "gs_chats": "Chats", "gs_msgs": "Messages",
        "cat_photos": "📷 Photos", "cat_videos": "🎬 Videos", "cat_links": "🔗 Links",
        "cat_music": "🎵 Music", "cat_contacts": "👤 Contacts",
        "wp_fish": "Fish 🐟", "wp_hearts": "Hearts 💕",
        "ctx_copy": "Copy text", "ctx_reply": "Reply", "ctx_fwd": "Forward",
        "ctx_del": "Delete", "ctx_pin": "Pin", "fwd_pick": "Forward to…",
        "fwd_ok": "Forwarded", "pin_ok": "Pinned", "del_ok": "Deleted",
        "replying": "Replying to a message", "profile": "Profile",
        "info_user": "Username", "info_phone": "Phone", "info_about": "Bio",
        "day_today": "Today",
        "set_trlang": "Translation language", "tr_input": "Translate what you write",
        "set_device": "Device (as Telegram sees us)", "dev_desktop": "Computer (CatGram)",
        "dev_android": "Android (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "Takes effect after restart", "set_notify": "Tray notifications",
        "set_nsound": "Notification sound", "set_stream": "Stream video (no full download)",
        "wp_file": "From computer 📁", "set_wall_pick": "Choose file…",
        "play_app": "Play (bot mini-app)", "not_bot": "Not a bot: mini-apps live in bot chats",
        "set_catcursor": "Cat cursor with a stick 🐱",
        "turn_black": "Black's turn", "in_check": "Check!", "white_wins": "White wins!",
        "black_wins": "Black wins!", "stalemate": "Stalemate — draw",
        "must_capture": "Captures are mandatory!",
        "xo_win": "You won!", "xo_lose": "The cat won",
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
        "set_noise": "Шумоподавление в звонках",
        "set_wallpaper": "Обои чата", "wp_none": "Нет", "wp_paws": "Лапки 🐾",
        "wp_stars": "Звёздочки ✨",
        "noise_off": "Шумоподавление недоступно",
        "noise_on": "Шумоподавление: {name}", "test_noise": "Проверить",
        "accounts": "Аккаунты…", "acc_add": "Добавить аккаунт",
        "acc_switch": "Переключиться", "acc_remove": "Удалить",
        "acc_del_q": "Удалить аккаунт {name}?",
        "acc_switch_q": "Перезапустить catgram и переключиться на «{name}»?",
        "acc_limit": "Достигнут лимит: 100 дополнительных аккаунтов",
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
        "tetris": "🧱 Котетрис", "lines": "Линий",
        "tetris_hint": "←→↓ — движение · ↑ — поворот · Пробел — сброс · P — пауза",
        "mines": "💣 Сапёр",
        "mines_hint": "ЛКМ — открыть · ПКМ — флаг · R — заново",
        "win": "Победа!", "lose": "Поражение", "draw": "Ничья",
        "cards": "🃏 Пьяница", "card_ranks": "6 7 8 9 10 В Д К Т",
        "cards_you": "Ты", "cards_cat": "Кот",
        "cards_move": "Клик или Пробел — раунд",
        "cards_war": "⚔️ Спор! Карты остаются на столе",
        "mario": "🐱 Суперкот", "lives": "Жизни", "coins": "Монеты",
        "mario_hint": "←→ — бег · ↑ / Пробел — прыжок · прыгай на мышей!",
        "kart": "🏎 Котокарт", "lap": "Круг", "place": "Место",
        "kart_hint": "↑ — газ · ←→ — руль · ↓ — тормоз",
        "arka": "🧱 Котаноид",
        "arka_hint": "Мышь / ←→ — ракетка · не урони мяч",
        "g15": "🧩 Пятнашки", "moves": "Ходов", "solved": "Собрано!",
        "pairs": "🎴 Найди пару",
        "xo": "⭕ Крестики-нолики", "xo_you": "Твой ход", "xo_cat": "Ход кота",
        "chess": "♞ Шахматы", "checkers": "Шашки", "turn_white": "Ход белых",
        "tanks": "▮ Танки", "gsearch": "Глобальный поиск", "media_search": "Медиа переписки",
        "translate_chat": "Перевести переписку", "translating": "Перевожу…",
        "gs_hint": "Поиск по всем чатам и сообщениям",
        "gs_chats": "Чаты", "gs_msgs": "Сообщения",
        "cat_photos": "📷 Фото", "cat_videos": "🎬 Видео", "cat_links": "🔗 Ссылки",
        "cat_music": "🎵 Музыка", "cat_contacts": "👤 Контакты",
        "wp_fish": "Рыбки 🐟", "wp_hearts": "Сердечки 💕",
        "ctx_copy": "Копировать текст", "ctx_reply": "Ответить", "ctx_fwd": "Переслать",
        "ctx_del": "Удалить", "ctx_pin": "Закрепить", "fwd_pick": "Переслать в…",
        "fwd_ok": "Переслано", "pin_ok": "Закреплено", "del_ok": "Удалено",
        "replying": "Ответ на сообщение", "profile": "Профиль",
        "info_user": "Имя пользователя", "info_phone": "Телефон", "info_about": "О себе",
        "day_today": "Сегодня",
        "set_trlang": "Язык перевода", "tr_input": "Перевести набранное сообщение",
        "set_device": "Устройство (клиент)", "dev_desktop": "Компьютер (CatGram)",
        "dev_android": "Android (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "Применится после перезапуска", "set_notify": "Уведомления в трее",
        "set_nsound": "Звук уведомлений", "set_stream": "Видео без скачивания (стрим)",
        "wp_file": "С компьютера 📁", "set_wall_pick": "Выбрать файл…",
        "play_app": "Играть (мини-приложение бота)",
        "not_bot": "Это не бот: мини-приложения бывают только у ботов",
        "set_catcursor": "Курсор-кот с палочкой 🐱",
        "turn_black": "Ход чёрных", "in_check": "Шах!", "white_wins": "Белые победили!",
        "black_wins": "Чёрные победили!", "stalemate": "Пат — ничья",
        "must_capture": "Взятие обязательно!",
        "xo_win": "Ты выиграл!", "xo_lose": "Кот выиграл",
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
        "set_noise": "Придушення шуму в дзвінках",
        "set_wallpaper": "Шпалери чату", "wp_none": "Немає", "wp_paws": "Лапки 🐾",
        "wp_stars": "Зірочкі ✨",
        "noise_off": "Придушення шуму недоступне",
        "noise_on": "Придушення шуму: {name}", "test_noise": "Перевірити",
        "accounts": "Акаунти…", "acc_add": "Додати акаунт",
        "acc_switch": "Перемкнутися", "acc_remove": "Видалити",
        "acc_del_q": "Видалити акаунт {name}?",
        "acc_switch_q": "Перезапустити catgram і перемкнутися на «{name}»?",
        "acc_limit": "Досягнуто ліміт: 100 додаткових акаунтів",
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
        "tetris": "🧱 Котетріс", "lines": "Ліній",
        "tetris_hint": "←→↓ — рух · ↑ — поворот · Пробіл — скинути · P — пауза",
        "mines": "💣 Сапер",
        "mines_hint": "ЛКМ — відкрити · ПКМ — прапорець · R — заново",
        "win": "Перемога!", "lose": "Поразка", "draw": "Нічия",
        "cards": "🃏 П’яниця", "card_ranks": "6 7 8 9 10 В Д К Т",
        "cards_you": "Ти", "cards_cat": "Кіт",
        "cards_move": "Клік або Пробіл — раунд",
        "cards_war": "⚔️ Суперечка! Карти залишаються на столі",
        "mario": "🐱 Суперкіт", "lives": "Життя", "coins": "Монети",
        "mario_hint": "←→ — біг · ↑ / Пробіл — стрибок · стрибай на мишей!",
        "kart": "🏎 Котокарт", "lap": "Коло", "place": "Місце",
        "kart_hint": "↑ — газ · ←→ — кермо · ↓ — гальмо",
        "arka": "🧱 Котаноїд",
        "arka_hint": "Миша / ←→ — ракетка · не впусти мʼяч",
        "g15": "🧩 П’ятнашки", "moves": "Ходів", "solved": "Зібрано!",
        "pairs": "🎴 Знайди пару",
        "xo": "⭕ Хрестики-нулики", "xo_you": "Ваш хід", "xo_cat": "Хід кота",
        "chess": "♞ Шахи", "checkers": "Шашки", "turn_white": "Хід білих",
        "tanks": "▮ Танки", "gsearch": "Глобальний пошук", "media_search": "Медіа переписки",
        "translate_chat": "Перекласти переписку", "translating": "Перекладаю…",
        "gs_hint": "Пошук по всіх чатах і повідомленнях",
        "gs_chats": "Чати", "gs_msgs": "Повідомлення",
        "cat_photos": "📷 Фото", "cat_videos": "🎬 Відео", "cat_links": "🔗 Посилання",
        "cat_music": "🎵 Музика", "cat_contacts": "👤 Контакти",
        "wp_fish": "Рибки 🐟", "wp_hearts": "Серденька 💕",
        "ctx_copy": "Копіювати текст", "ctx_reply": "Відповісти", "ctx_fwd": "Переслати",
        "ctx_del": "Видалити", "ctx_pin": "Закріпити", "fwd_pick": "Переслати до…",
        "fwd_ok": "Переслано", "pin_ok": "Закріплено", "del_ok": "Видалено",
        "replying": "Відповідь на повідомлення", "profile": "Профіль",
        "info_user": "Ім'я користувача", "info_phone": "Телефон", "info_about": "Про себе",
        "day_today": "Сьогодні",
        "set_trlang": "Мова перекладу", "tr_input": "Перекласти набране повідомлення",
        "set_device": "Пристрій (клієнт)", "dev_desktop": "Комп'ютер (CatGram)",
        "dev_android": "Android (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "Застосується після перезапуску", "set_notify": "Сповіщення в треї",
        "set_nsound": "Звук сповіщень", "set_stream": "Відео без завантаження (стрим)",
        "wp_file": "З комп'ютера 📁", "set_wall_pick": "Вибрати файл…",
        "play_app": "Грати (міні-застосунок бота)",
        "not_bot": "Це не бот: міні-застосунки бувають лише у ботів",
        "set_catcursor": "Курсор-кішка з паличкою 🐱",
        "turn_black": "Хід чорних", "in_check": "Шах!", "white_wins": "Білі перемогли!",
        "black_wins": "Чорні перемогли!", "stalemate": "Пат — нічия",
        "must_capture": "Взяття обов'язкове!",
        "xo_win": "Ти виграв!", "xo_lose": "Кіт виграв",
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
    "es": {
        "title": "🐱 catgram", "login": "🐱 catgram — iniciar sesión",
        "api_id": "api_id (my.telegram.org → API development tools):",
        "api_hash": "api_hash:",
        "phone": "Número de teléfono (+código de país y número):",
        "bad_phone": "Número no válido. Usa el formato internacional: "
                     "+<código de país><número> (sin 0 inicial), p. ej. +12025550123",
        "code": "Código de Telegram:", "bad_code": "Código incorrecto, inténtalo de nuevo:",
        "pw": "Contraseña de verificación en dos pasos:",
        "bad_pw": "Contraseña incorrecta, otra vez:",
        "write": "Miau… escribe un mensaje y pulsa Enter",
        "find_chats": "Buscar chats…",
        "find_msgs": "Buscar en este chat… (Enter — buscar, Esc — cerrar)",
        "pick_chat": "Elige un chat a la izquierda", "menu": "catgram",
        "settings": "Ajustes…", "accounts": "Cuentas…", "search": "Buscar en el chat",
        "updates": "Buscar actualizaciones", "quit": "Salir", "me": "Yo",
        "m_sticker": "[sticker]", "m_photo": "[foto]", "m_voice": "[nota de voz]",
        "m_video": "[vídeo]", "m_file": "[archivo]", "m_other": "[adjunto]",
        "set_title": "Ajustes", "set_lang": "Idioma", "set_theme": "Tema",
        "theme_dark": "Oscuro", "theme_light": "Claro", "set_font": "Tamaño de letra",
        "set_avatars": "Avatares", "av_real": "Fotos reales (gato si no hay)",
        "av_cats": "Solo gatos", "av_none": "Sin avatares",
        "set_photos": "Mostrar imágenes en el chat",
        "set_noise": "Supresión de ruido en llamadas",
        "set_wallpaper": "Fondo del chat", "wp_none": "Ninguno", "wp_paws": "Huellitas 🐾",
        "wp_stars": "Estrellas ✨",
        "noise_off": "Supresión de ruido no disponible",
        "noise_on": "Supresión de ruido: {name}", "test_noise": "Probar",
        "acc_add": "Añadir cuenta", "acc_switch": "Cambiar", "acc_remove": "Eliminar",
        "acc_del_q": "¿Eliminar la cuenta {name}?",
        "acc_switch_q": "¿Reiniciar catgram y cambiar a {name}?",
        "acc_limit": "Límite alcanzado: 100 cuentas adicionales",
        "info": "Información del chat", "about": "Descripción",
        "username": "Usuario", "phone_lbl": "Teléfono", "members": "Miembros",
        "set_upd_start": "Buscar actualizaciones al iniciar",
        "set_upd_url": "URL de actualizaciones (https)",
        "upd_no_url": "No hay URL de actualizaciones. Añádela en Ajustes.",
        "upd_latest": "Tienes la última versión.", "upd_new": "Nueva versión disponible",
        "upd_err": "No se pudo comprobar actualizaciones",
        "res": "Resultados de búsqueda", "nothing": "No se encontró nada",
        "online": "ronroneando", "offline": "no ronronea",
        "attach_video": "Enviar un vídeo", "pick_video": "Elige un vídeo",
        "video_files": "Vídeo", "all_files": "Todos los archivos",
        "sending_video": "Enviando vídeo",
        "hist_start": "· principio de la conversación ·",
        "hist_loading": "Cargando historial…", "error": "Error",
        "games": "🎮 Juegos", "snake": "🐍 Serpiente", "g2048": "🐾 2048",
        "emoji": "Emojis", "score": "Puntos", "best": "Récord",
        "game_over": "Fin del juego", "paused": "Pausa",
        "again": "Pulsa R para jugar otra vez",
        "game_hint": "Espacio — pausa · R — nueva partida",
        "wait_hint": "Juega mientras esperas respuesta 🐾",
        "tetris": "🧱 Gatetris", "lines": "Líneas",
        "tetris_hint": "←→↓ — mover · ↑ — girar · Espacio — soltar · P — pausa",
        "mines": "💣 Buscaminas",
        "mines_hint": "Clic izq. — abrir · clic der. — bandera · R — nueva partida",
        "win": "¡Ganas!", "lose": "Pierdes", "draw": "Empate",
        "cards": "🃏 Guerra", "card_ranks": "6 7 8 9 10 J Q K A",
        "cards_you": "Tú", "cards_cat": "Gato",
        "cards_move": "Clic o Espacio — siguiente ronda",
        "cards_war": "⚔️ ¡Guerra! Las cartas se quedan en la mesa",
        "mario": "🐱 Súper Gato", "lives": "Vidas", "coins": "Monedas",
        "mario_hint": "←→ — correr · ↑ / Espacio — saltar · ¡pisa los ratones!",
        "kart": "🏎 Gato-Kart", "lap": "Vuelta", "place": "Puesto",
        "kart_hint": "↑ — gas · ←→ — volante · ↓ — freno",
        "arka": "🧱 Gatanoide",
        "arka_hint": "Ratón / ←→ — pala · no dejes caer la bola",
        "g15": "🧩 Puzzle de 15", "moves": "Movimientos", "solved": "¡Resuelto!",
        "pairs": "🎴 Encuentra parejas",
        "xo": "⭕ Tres en raya", "xo_you": "Tu turno", "xo_cat": "Turno del gato",
        "chess": "♞ Ajedrez", "checkers": "Damas", "turn_white": "Turno de blancas",
        "tanks": "▮ Tanques", "gsearch": "Búsqueda global", "media_search": "Multimedia del chat",
        "translate_chat": "Traducir el chat", "translating": "Traduciendo…",
        "gs_hint": "Busca en todos los chats y mensajes",
        "gs_chats": "Chats", "gs_msgs": "Mensajes",
        "cat_photos": "📷 Fotos", "cat_videos": "🎬 Vídeos", "cat_links": "🔗 Enlaces",
        "cat_music": "🎵 Música", "cat_contacts": "👤 Contactos",
        "wp_fish": "Peces 🐟", "wp_hearts": "Corazones 💕",
        "ctx_copy": "Copiar texto", "ctx_reply": "Responder", "ctx_fwd": "Reenviar",
        "ctx_del": "Eliminar", "ctx_pin": "Fijar", "fwd_pick": "Reenviar a…",
        "fwd_ok": "Reenviado", "pin_ok": "Fijado", "del_ok": "Eliminado",
        "replying": "Responder al mensaje", "profile": "Perfil",
        "info_user": "Usuario", "info_phone": "Teléfono", "info_about": "Biografía",
        "day_today": "Hoy",
        "set_trlang": "Idioma de traducción", "tr_input": "Traducir lo que escribes",
        "set_device": "Dispositivo (cliente)", "dev_desktop": "Ordenador (CatGram)",
        "dev_android": "Android (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "Se aplica tras reiniciar", "set_notify": "Notificaciones en la bandeja",
        "set_nsound": "Sonido de las notificaciones",
        "set_stream": "Vídeo en streaming (sin descarga)",
        "wp_file": "Del ordenador 📁", "set_wall_pick": "Elegir archivo…",
        "play_app": "Jugar (mini-app del bot)",
        "not_bot": "No es un bot: las mini-apps solo están en bots",
        "set_catcursor": "Cursor de gatito con palito 🐱",
        "turn_black": "Turno de negras", "in_check": "¡Jaque!",
        "white_wins": "¡Ganan las blancas!", "black_wins": "¡Ganan las negras!",
        "stalemate": "Rey ahogado — tablas", "must_capture": "¡Captura obligatoria!",
        "xo_win": "¡Ganaste!", "xo_lose": "Ganó el gato",
        "stickers": "Stickers", "st_load": "Cargando stickers…",
        "st_none": "No hay packs de stickers", "st_fail": "No se pudieron cargar vistas previas",
        "st_webp": "Esta compilación de Qt no lee WebP — los stickers no se verán. "
                   "Instala dwebp (paquete libwebp-tools), ffmpeg o ImageMagick",
        "call": "Llamar por Telegram", "call_tel": "Llamar por teléfono (tel:)",
        "call_title": "Llamada",
        "call_need_lib": "Las llamadas necesitan la biblioteca ntgcalls.<br>"
                         "Instálala: <code>pip install ntgcalls</code>",
        "call_no_audio": "No se encontró micrófono ni altavoces",
        "call_hint_throw": "No se pudo obtener la lista de dispositivos de audio: {err}",
        "call_hint_libs": "No se encontraron las bibliotecas de sonido del sistema. "
                          "Instálalas y reinicia catgram:\nDebian/Ubuntu: sudo apt install "
                          "libpulse0 libasound2\nFedora: sudo dnf install pulseaudio-libs "
                          "alsa-lib\nArch: sudo pacman -S libpulse alsa-lib\n"
                          "Comprueba en la terminal: ldconfig -p | grep libpulse",
        "call_hint_server": "El servidor de sonido (PulseAudio/PipeWire) no es accesible "
                            "desde esta sesión. Inicia catgram desde un terminal normal "
                            "del escritorio (no por SSH, no con sudo) y verifica que el "
                            "sonido del sistema funciona.",
        "call_hint_pactl": "El servidor de sonido parece funcionar, pero ntgcalls no ve "
                           "dispositivos. Ejecuta en el mismo terminal: pactl list short — "
                           "y envía la salida al desarrollador.",
        "call_hint_mic": "No se ve el micrófono (sí se hallaron altavoces). Conecta un "
                         "micrófono o actívalo en los ajustes de sonido del sistema.",
        "call_hint_spk": "No se ven los altavoces (se halló micrófono). Comprueba los "
                         "dispositivos de salida en los ajustes de sonido del sistema.",
        "call_bad_lib": "La ntgcalls {ver} instalada no sirve: falta {missing}.<br>"
                        "Prueba <code>pip install -U ntgcalls</code> (en el mismo entorno "
                        "donde se ejecuta catgram). Si no ayuda, envía este texto al "
                        "desarrollador:<br>{have}",
        "call_busy": "Ya hay otra llamada en curso",
        "call_no_phone": "El número de teléfono no es visible (privacidad)",
        "call_people_only": "Solo se puede llamar a chats con personas",
        "call_tel_fail": "Ninguna aplicación abre enlaces tel:. Instala una (p. ej. "
                         "KDE Connect / GSConnect) o marca el número a mano.",
        "call_dialing": "Llamando…", "call_incoming": "Llamada entrante…",
        "call_connecting": "Conectando…", "call_talking": "En llamada",
        "call_accept": "Aceptar", "call_decline": "Rechazar", "call_end": "Colgar",
        "call_mute": "Silenciar micrófono", "call_unmute": "Activar micrófono",
        "call_ended": "Llamada finalizada", "call_missed": "Sin respuesta",
        "call_peer_busy": "Rechazada u ocupada", "call_failed": "Conexión perdida",
    },
    "fr": {
        "title": "🐱 catgram", "login": "🐱 catgram — connexion",
        "api_id": "api_id (my.telegram.org → API development tools) :",
        "api_hash": "api_hash :",
        "phone": "Numéro de téléphone (+indicatif et numéro) :",
        "bad_phone": "Numéro invalide. Format international : "
                     "+<indicatif><numéro> (sans 0 initial), ex. +12025550123",
        "code": "Code de Telegram :", "bad_code": "Code incorrect, réessaie :",
        "pw": "Mot de passe de vérification en deux étapes :",
        "bad_pw": "Mot de passe incorrect, encore :",
        "write": "Miaou… écris un message et appuie sur Entrée",
        "find_chats": "Rechercher des discussions…",
        "find_msgs": "Rechercher dans ce chat… (Entrée — chercher, Échap — fermer)",
        "pick_chat": "Choisis une discussion à gauche", "menu": "catgram",
        "settings": "Réglages…", "accounts": "Comptes…", "search": "Rechercher dans le chat",
        "updates": "Vérifier les mises à jour", "quit": "Quitter", "me": "Moi",
        "m_sticker": "[sticker]", "m_photo": "[photo]", "m_voice": "[vocal]",
        "m_video": "[vidéo]", "m_file": "[fichier]", "m_other": "[pièce jointe]",
        "set_title": "Réglages", "set_lang": "Langue", "set_theme": "Thème",
        "theme_dark": "Sombre", "theme_light": "Clair", "set_font": "Taille de police",
        "set_avatars": "Avatars", "av_real": "Photos réelles (chat si absent)",
        "av_cats": "Chats seulement", "av_none": "Sans avatars",
        "set_photos": "Afficher les images dans le chat",
        "set_noise": "Suppression du bruit dans les appels",
        "set_wallpaper": "Fond de discussion", "wp_none": "Aucun", "wp_paws": "Pattes 🐾",
        "wp_stars": "Étoiles ✨",
        "noise_off": "Suppression du bruit indisponible",
        "noise_on": "Suppression du bruit : {name}", "test_noise": "Tester",
        "acc_add": "Ajouter un compte", "acc_switch": "Basculer", "acc_remove": "Supprimer",
        "acc_del_q": "Supprimer le compte {name} ?",
        "acc_switch_q": "Redémarrer catgram et basculer vers {name} ?",
        "acc_limit": "Limite atteinte : 100 comptes supplémentaires",
        "info": "Infos du chat", "about": "Description",
        "username": "Nom d'utilisateur", "phone_lbl": "Téléphone", "members": "Membres",
        "set_upd_start": "Vérifier les mises à jour au démarrage",
        "set_upd_url": "URL des mises à jour (https)",
        "upd_no_url": "Aucune URL de mise à jour. Ajoute-la dans les Réglages.",
        "upd_latest": "Tu as la dernière version.", "upd_new": "Nouvelle version disponible",
        "upd_err": "Impossible de vérifier les mises à jour",
        "res": "Résultats de recherche", "nothing": "Rien trouvé",
        "online": "ronronne", "offline": "ne ronronne pas",
        "attach_video": "Envoyer une vidéo", "pick_video": "Choisis une vidéo",
        "video_files": "Vidéo", "all_files": "Tous les fichiers",
        "sending_video": "Envoi de la vidéo",
        "hist_start": "· début de la conversation ·",
        "hist_loading": "Chargement de l'historique…", "error": "Erreur",
        "games": "🎮 Jeux", "snake": "🐍 Serpent", "g2048": "🐾 2048",
        "emoji": "Émojis", "score": "Score", "best": "Record",
        "game_over": "Partie terminée", "paused": "Pause",
        "again": "Appuie sur R pour rejouer",
        "game_hint": "Espace — pause · R — nouvelle partie",
        "wait_hint": "Joue en attendant la réponse 🐾",
        "tetris": "🧱 Chattris", "lines": "Lignes",
        "tetris_hint": "←→↓ — déplacer · ↑ — pivoter · Espace — lâcher · P — pause",
        "mines": "💣 Démineur",
        "mines_hint": "Clic gauche — ouvrir · clic droit — drapeau · R — nouvelle partie",
        "win": "Tu gagnes !", "lose": "Tu perds", "draw": "Égalité",
        "cards": "🃏 Bataille", "card_ranks": "6 7 8 9 10 V D R As",
        "cards_you": "Toi", "cards_cat": "Chat",
        "cards_move": "Clic ou Espace — manche suivante",
        "cards_war": "⚔️ Bataille ! Les cartes restent sur la table",
        "mario": "🐱 Super Chat", "lives": "Vies", "coins": "Pièces",
        "mario_hint": "←→ — courir · ↑ / Espace — sauter · écrase les souris !",
        "kart": "🏎 Chat-Kart", "lap": "Tour", "place": "Place",
        "kart_hint": "↑ — gaz · ←→ — volant · ↓ — frein",
        "arka": "🧱 Cassanoï",
        "arka_hint": "Souris / ←→ — raquette · ne laisse pas tomber la balle",
        "g15": "🧩 Taquin", "moves": "Coups", "solved": "Résolu !",
        "pairs": "🎨 Trouve les paires",
        "xo": "⭕ Morpion", "xo_you": "À toi", "xo_cat": "Au chat",
        "chess": "♞ Échecs", "checkers": "Dames", "turn_white": "Aux blancs",
        "tanks": "▮ Chars", "gsearch": "Recherche globale", "media_search": "Médias de la discussion",
        "translate_chat": "Traduire la discussion", "translating": "Traduction…",
        "gs_hint": "Rechercher dans toutes les discussions",
        "gs_chats": "Discussions", "gs_msgs": "Messages",
        "cat_photos": "📷 Photos", "cat_videos": "🎬 Vidéos", "cat_links": "🔗 Liens",
        "cat_music": "🎵 Musique", "cat_contacts": "👤 Contacts",
        "wp_fish": "Poissons 🐟", "wp_hearts": "Cœurs 💕",
        "ctx_copy": "Copier le texte", "ctx_reply": "Répondre", "ctx_fwd": "Transférer",
        "ctx_del": "Supprimer", "ctx_pin": "Épingler", "fwd_pick": "Transférer à…",
        "fwd_ok": "Transféré", "pin_ok": "Épinglé", "del_ok": "Supprimé",
        "replying": "Réponse au message", "profile": "Profil",
        "info_user": "Nom d'utilisateur", "info_phone": "Téléphone", "info_about": "Bio",
        "day_today": "Aujourd'hui",
        "set_trlang": "Langue de traduction", "tr_input": "Traduire ce que vous écrivez",
        "set_device": "Appareil (client)", "dev_desktop": "Ordinateur (CatGram)",
        "dev_android": "Android (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "Appliqué après redémarrage",
        "set_notify": "Notifications dans la barre système",
        "set_nsound": "Son des notifications",
        "set_stream": "Vidéo en streaming (sans téléchargement)",
        "wp_file": "Depuis l'ordinateur 📁", "set_wall_pick": "Choisir un fichier…",
        "play_app": "Jouer (mini-app du bot)",
        "not_bot": "Ce n'est pas un bot : les mini-apps sont chez les bots",
        "set_catcursor": "Curseur chaton avec baguette 🐱",
        "turn_black": "Aux noirs", "in_check": "Échec !",
        "white_wins": "Les blancs gagnent !", "black_wins": "Les noirs gagnent !",
        "stalemate": "Pat — nulle", "must_capture": "Prise obligatoire !",
        "xo_win": "Tu as gagné !", "xo_lose": "Le chat a gagné",
        "stickers": "Stickers", "st_load": "Chargement des stickers…",
        "st_none": "Aucun pack de stickers", "st_fail": "Échec du chargement des vignettes",
        "st_webp": "Cette compilation de Qt ne lit pas le WebP — les stickers ne "
                   "s'afficheront pas. Installe dwebp (paquet libwebp-tools), ffmpeg "
                   "ou ImageMagick",
        "call": "Appeler via Telegram", "call_tel": "Appeler le numéro (tel:)",
        "call_title": "Appel",
        "call_need_lib": "Les appels nécessitent la bibliothèque ntgcalls.<br>"
                         "Installe-la : <code>pip install ntgcalls</code>",
        "call_no_audio": "Aucun micro ni haut-parleur trouvé",
        "call_hint_throw": "Impossible d'obtenir la liste des périphériques audio : {err}",
        "call_hint_libs": "Bibliothèques son du système introuvables. Installe-les et "
                          "relance catgram :\nDebian/Ubuntu : sudo apt install libpulse0 "
                          "libasound2\nFedora : sudo dnf install pulseaudio-libs alsa-lib\n"
                          "Arch : sudo pacman -S libpulse alsa-lib\n"
                          "Vérifie dans le terminal : ldconfig -p | grep libpulse",
        "call_hint_server": "Le serveur son (PulseAudio/PipeWire) est inaccessible depuis "
                            "cette session. Lance catgram depuis un terminal normal du "
                            "bureau (pas via SSH, pas via sudo) et vérifie que le son "
                            "fonctionne.",
        "call_hint_pactl": "Le serveur son semble tourner, mais ntgcalls ne voit aucun "
                           "périphérique. Lance dans le même terminal : pactl list short — "
                           "et envoie la sortie au développeur.",
        "call_hint_mic": "Pas de micro visible (des haut-parleurs ont été trouvés). "
                         "Branche un micro ou active-le dans les réglages son du système.",
        "call_hint_spk": "Pas de haut-parleurs visibles (un micro a été trouvé). Vérifie "
                         "les périphériques de sortie dans les réglages son du système.",
        "call_bad_lib": "La ntgcalls {ver} installée ne convient pas : il manque "
                        "{missing}.<br>Essaie <code>pip install -U ntgcalls</code> (dans "
                        "le même environnement que catgram). Sinon, envoie ce texte au "
                        "développeur :<br>{have}",
        "call_busy": "Un autre appel est déjà en cours",
        "call_no_phone": "Le numéro n'est pas visible (paramètres de confidentialité)",
        "call_people_only": "Les appels ne sont possibles qu'avec des personnes",
        "call_tel_fail": "Aucune application n'ouvre les liens tel:. Installe-en une "
                         "(ex. KDE Connect / GSConnect) ou compose le numéro à la main.",
        "call_dialing": "Appel…", "call_incoming": "Appel entrant…",
        "call_connecting": "Connexion…", "call_talking": "En appel",
        "call_accept": "Accepter", "call_decline": "Refuser", "call_end": "Raccrocher",
        "call_mute": "Couper le micro", "call_unmute": "Activer le micro",
        "call_ended": "Appel terminé", "call_missed": "Pas de réponse",
        "call_peer_busy": "Refusé ou occupé", "call_failed": "Connexion perdue",
    },
    "de": {
        "title": "🐱 catgram", "login": "🐱 catgram — Anmeldung",
        "api_id": "api_id (my.telegram.org → API development tools):",
        "api_hash": "api_hash:",
        "phone": "Telefonnummer (+Ländervorwahl und Nummer):",
        "bad_phone": "Ungültige Nummer. Internationales Format verwenden: "
                     "+<Ländervorwahl><Nummer> (ohne führende 0), z. B. +12025550123",
        "code": "Code von Telegram:", "bad_code": "Falscher Code, nochmal:",
        "pw": "Passwort der Zwei-Faktor-Prüfung:",
        "bad_pw": "Falsches Passwort, nochmal:",
        "write": "Miau… schreibe eine Nachricht und drücke Enter",
        "find_chats": "Chats suchen…",
        "find_msgs": "In diesem Chat suchen… (Enter — suchen, Esc — schließen)",
        "pick_chat": "Wähle links einen Chat", "menu": "catgram",
        "settings": "Einstellungen…", "accounts": "Konten…", "search": "Im Chat suchen",
        "updates": "Nach Updates suchen", "quit": "Beenden", "me": "Ich",
        "m_sticker": "[Sticker]", "m_photo": "[Foto]", "m_voice": "[Sprachnachricht]",
        "m_video": "[Video]", "m_file": "[Datei]", "m_other": "[Anhang]",
        "set_title": "Einstellungen", "set_lang": "Sprache", "set_theme": "Design",
        "theme_dark": "Dunkel", "theme_light": "Hell", "set_font": "Schriftgröße",
        "set_avatars": "Avatare", "av_real": "Echte Fotos (sonst Katze)",
        "av_cats": "Nur Katzen", "av_none": "Ohne Avatare",
        "set_photos": "Bilder im Chat anzeigen",
        "set_noise": "Rauschunterdrückung bei Anrufen",
        "set_wallpaper": "Chat-Hintergrund", "wp_none": "Keins", "wp_paws": "Pfötchen 🐾",
        "wp_stars": "Sterne ✨",
        "noise_off": "Rauschunterdrückung nicht verfügbar",
        "noise_on": "Rauschunterdrückung: {name}", "test_noise": "Testen",
        "acc_add": "Konto hinzufügen", "acc_switch": "Wechseln", "acc_remove": "Entfernen",
        "acc_del_q": "Konto {name} entfernen?",
        "acc_switch_q": "catgram neu starten und zu {name} wechseln?",
        "acc_limit": "Limit erreicht: 100 zusätzliche Konten",
        "info": "Chat-Info", "about": "Beschreibung",
        "username": "Benutzername", "phone_lbl": "Telefon", "members": "Mitglieder",
        "set_upd_start": "Beim Start nach Updates suchen",
        "set_upd_url": "Update-Adresse (https)",
        "upd_no_url": "Keine Update-Adresse gesetzt. Trage sie in den Einstellungen ein.",
        "upd_latest": "Du hast die neueste Version.", "upd_new": "Neue Version verfügbar",
        "upd_err": "Updates konnten nicht geprüft werden",
        "res": "Suchergebnisse", "nothing": "Nichts gefunden",
        "online": "schnurrt", "offline": "schnurrt nicht",
        "attach_video": "Video senden", "pick_video": "Video auswählen",
        "video_files": "Video", "all_files": "Alle Dateien",
        "sending_video": "Video wird gesendet",
        "hist_start": "· Anfang der Unterhaltung ·",
        "hist_loading": "Verlauf wird geladen…", "error": "Fehler",
        "games": "🎮 Spiele", "snake": "🐍 Schlange", "g2048": "🐾 2048",
        "emoji": "Emojis", "score": "Punkte", "best": "Rekord",
        "game_over": "Spiel vorbei", "paused": "Pause",
        "again": "Drücke R für ein neues Spiel",
        "game_hint": "Leertaste — Pause · R — neues Spiel",
        "wait_hint": "Spiele, während du auf eine Antwort wartest 🐾",
        "tetris": "🧱 Katzetris", "lines": "Linien",
        "tetris_hint": "←→↓ — bewegen · ↑ — drehen · Leertaste — fallen · P — Pause",
        "mines": "💣 Minesweeper",
        "mines_hint": "Linksklick — öffnen · Rechtsklick — Fahne · R — neues Spiel",
        "win": "Du gewinnst!", "lose": "Du verlierst", "draw": "Unentschieden",
        "cards": "🃏 Krieg", "card_ranks": "6 7 8 9 10 B D K Ass",
        "cards_you": "Du", "cards_cat": "Katze",
        "cards_move": "Klick oder Leertaste — nächste Runde",
        "cards_war": "⚔️ Krieg! Die Karten bleiben auf dem Tisch",
        "mario": "🐱 Superkatze", "lives": "Leben", "coins": "Münzen",
        "mario_hint": "←→ — laufen · ↑ / Leertaste — springen · spring auf die Mäuse!",
        "kart": "🏎 Katzen-Kart", "lap": "Runde", "place": "Platz",
        "kart_hint": "↑ — Gas · ←→ — lenken · ↓ — Bremse",
        "arka": "🧱 Katanoid",
        "arka_hint": "Maus / ←→ — Schläger · lass den Ball nicht fallen",
        "g15": "🧩 15-Puzzle", "moves": "Züge", "solved": "Gelöst!",
        "pairs": "🎴 Paare finden",
        "xo": "⭕ Drei gewinnt", "xo_you": "Du bist dran", "xo_cat": "Katze ist dran",
        "chess": "♞ Schach", "checkers": "Dame", "turn_white": "Weiß am Zug",
        "tanks": "▮ Panzer", "gsearch": "Globale Suche", "media_search": "Medien im Chat",
        "translate_chat": "Chat übersetzen", "translating": "Übersetze…",
        "gs_hint": "In allen Chats und Nachrichten suchen",
        "gs_chats": "Chats", "gs_msgs": "Nachrichten",
        "cat_photos": "📷 Fotos", "cat_videos": "🎬 Videos", "cat_links": "🔗 Links",
        "cat_music": "🎵 Musik", "cat_contacts": "👤 Kontakte",
        "wp_fish": "Fische 🐟", "wp_hearts": "Herzen 💕",
        "ctx_copy": "Text kopieren", "ctx_reply": "Antworten", "ctx_fwd": "Weiterleiten",
        "ctx_del": "Löschen", "ctx_pin": "Anheften", "fwd_pick": "Weiterleiten an…",
        "fwd_ok": "Weitergeleitet", "pin_ok": "Angeheftet", "del_ok": "Gelöscht",
        "replying": "Antwort auf Nachricht", "profile": "Profil",
        "info_user": "Benutzername", "info_phone": "Telefon", "info_about": "Bio",
        "day_today": "Heute",
        "set_trlang": "Übersetzungssprache", "tr_input": "Übersetze, was du schreibst",
        "set_device": "Gerät (Client)", "dev_desktop": "Rechner (CatGram)",
        "dev_android": "Android (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "Wirkt nach dem Neustart", "set_notify": "Tray-Benachrichtigungen",
        "set_nsound": "Benachrichtigungston",
        "set_stream": "Video streamen (ohne vollständigen Download)",
        "wp_file": "Vom Computer 📁", "set_wall_pick": "Datei auswählen…",
        "play_app": "Spielen (Mini-App des Bots)",
        "not_bot": "Das ist kein Bot: Mini-Apps gibt es nur bei Bots",
        "set_catcursor": "Kätzchen-Cursor mit Stöckchen 🐱",
        "turn_black": "Schwarz am Zug", "in_check": "Schach!",
        "white_wins": "Weiß gewinnt!", "black_wins": "Schwarz gewinnt!",
        "stalemate": "Patt — Remis", "must_capture": "Schlagen ist Pflicht!",
        "xo_win": "Du hast gewonnen!", "xo_lose": "Die Katze hat gewonnen",
        "stickers": "Sticker", "st_load": "Sticker werden geladen…",
        "st_none": "Keine Stickerpakete", "st_fail": "Vorschauen konnten nicht geladen werden",
        "st_webp": "Dieses Qt kann kein WebP lesen — Sticker erscheinen nicht. "
                   "Installiere dwebp (Paket libwebp-tools), ffmpeg oder ImageMagick",
        "call": "Über Telegram anrufen", "call_tel": "Telefonnummer anrufen (tel:)",
        "call_title": "Anruf",
        "call_need_lib": "Anrufe brauchen die Bibliothek ntgcalls.<br>"
                         "Installieren: <code>pip install ntgcalls</code>",
        "call_no_audio": "Kein Mikrofon oder Lautsprecher gefunden",
        "call_hint_throw": "Audiogeräteliste konnte nicht geholt werden: {err}",
        "call_hint_libs": "System-Soundbibliotheken wurden nicht gefunden. Installiere "
                          "sie und starte catgram neu:\nDebian/Ubuntu: sudo apt install "
                          "libpulse0 libasound2\nFedora: sudo dnf install pulseaudio-libs "
                          "alsa-lib\nArch: sudo pacman -S libpulse alsa-lib\n"
                          "Prüfen im Terminal: ldconfig -p | grep libpulse",
        "call_hint_server": "Der Soundserver (PulseAudio/PipeWire) ist aus dieser Sitzung "
                            "nicht erreichbar. Starte catgram aus einem normalen "
                            "Desktop-Terminal (nicht über SSH, nicht mit sudo) und prüfe, "
                            "dass Sound funktioniert.",
        "call_hint_pactl": "Der Soundserver läuft offenbar, aber ntgcalls sieht keine "
                           "Geräte. Führe im selben Terminal aus: pactl list short — und "
                           "schicke die Ausgabe an den Entwickler.",
        "call_hint_mic": "Kein Mikrofon sichtbar (Lautsprecher wurden gefunden). Schließe "
                         "ein Mikrofon an oder aktiviere es in den Soundeinstellungen.",
        "call_hint_spk": "Keine Lautsprecher sichtbar (ein Mikrofon wurde gefunden). "
                         "Prüfe die Ausgabegeräte in den Soundeinstellungen.",
        "call_bad_lib": "Das installierte ntgcalls {ver} passt nicht: es fehlt "
                        "{missing}.<br>Probiere <code>pip install -U ntgcalls</code> (in "
                        "derselben Umgebung wie catgram). Hilft das nicht, schicke diesen "
                        "Text an den Entwickler:<br>{have}",
        "call_busy": "Es läuft bereits ein anderer Anruf",
        "call_no_phone": "Die Telefonnummer ist nicht sichtbar (Privatsphäre)",
        "call_people_only": "Anrufe sind nur in Chats mit Personen möglich",
        "call_tel_fail": "Keine App öffnet tel:-Links. Installiere eine (z. B. KDE "
                         "Connect / GSConnect) oder wähle die Nummer manuell.",
        "call_dialing": "Anrufen…", "call_incoming": "Eingehender Anruf…",
        "call_connecting": "Verbinden…", "call_talking": "Im Gespräch",
        "call_accept": "Annehmen", "call_decline": "Ablehnen", "call_end": "Beenden",
        "call_mute": "Mikrofon stummschalten", "call_unmute": "Mikrofon aktivieren",
        "call_ended": "Anruf beendet", "call_missed": "Keine Antwort",
        "call_peer_busy": "Abgelehnt oder besetzt", "call_failed": "Verbindung verloren",
    },
    "it": {
        "title": "🐱 catgram", "login": "🐱 catgram — accesso",
        "api_id": "api_id (my.telegram.org → API development tools):",
        "api_hash": "api_hash:",
        "phone": "Numero di telefono (+prefisso internazionale e numero):",
        "bad_phone": "Numero non valido. Formato internazionale: "
                     "+<prefisso><numero> (senza 0 iniziale), es. +12025550123",
        "code": "Codice da Telegram:", "bad_code": "Codice sbagliato, riprova:",
        "pw": "Password della verifica in due passaggi:",
        "bad_pw": "Password sbagliata, ancora:",
        "write": "Miao… scrivi un messaggio e premi Invio",
        "find_chats": "Cerca chat…",
        "find_msgs": "Cerca in questa chat… (Invio — cerca, Esc — chiudi)",
        "pick_chat": "Scegli una chat a sinistra", "menu": "catgram",
        "settings": "Impostazioni…", "accounts": "Account…", "search": "Cerca nella chat",
        "updates": "Cerca aggiornamenti", "quit": "Esci", "me": "Io",
        "m_sticker": "[sticker]", "m_photo": "[foto]", "m_voice": "[vocale]",
        "m_video": "[video]", "m_file": "[file]", "m_other": "[allegato]",
        "set_title": "Impostazioni", "set_lang": "Lingua", "set_theme": "Tema",
        "theme_dark": "Scuro", "theme_light": "Chiaro", "set_font": "Dimensione testo",
        "set_avatars": "Avatar", "av_real": "Foto vere (gatto se assente)",
        "av_cats": "Solo gatti", "av_none": "Senza avatar",
        "set_photos": "Mostra le immagini in chat",
        "set_noise": "Riduzione del rumore nelle chiamate",
        "set_wallpaper": "Sfondo della chat", "wp_none": "Nessuno", "wp_paws": "Zampette 🐾",
        "wp_stars": "Stelle ✨",
        "noise_off": "Riduzione del rumore non disponibile",
        "noise_on": "Riduzione del rumore: {name}", "test_noise": "Test",
        "acc_add": "Aggiungi account", "acc_switch": "Cambia", "acc_remove": "Rimuovi",
        "acc_del_q": "Rimuovere l'account {name}?",
        "acc_switch_q": "Riavviare catgram e passare a {name}?",
        "acc_limit": "Limite raggiunto: 100 account aggiuntivi",
        "info": "Info sulla chat", "about": "Descrizione",
        "username": "Nome utente", "phone_lbl": "Telefono", "members": "Membri",
        "set_upd_start": "Cerca aggiornamenti all'avvio",
        "set_upd_url": "URL aggiornamenti (https)",
        "upd_no_url": "Nessun URL di aggiornamento. Aggiungilo nelle Impostazioni.",
        "upd_latest": "Hai l'ultima versione.", "upd_new": "Nuova versione disponibile",
        "upd_err": "Impossibile cercare aggiornamenti",
        "res": "Risultati della ricerca", "nothing": "Niente trovato",
        "online": "fa le fusa", "offline": "non fa le fusa",
        "attach_video": "Invia un video", "pick_video": "Scegli un video",
        "video_files": "Video", "all_files": "Tutti i file",
        "sending_video": "Invio del video",
        "hist_start": "· inizio della conversazione ·",
        "hist_loading": "Carico la cronologia…", "error": "Errore",
        "games": "🎮 Giochi", "snake": "🐍 Snake", "g2048": "🐾 2048",
        "emoji": "Emoji", "score": "Punti", "best": "Record",
        "game_over": "Partita finita", "paused": "Pausa",
        "again": "Premi R per rigiocare",
        "game_hint": "Spazio — pausa · R — nuova partita",
        "wait_hint": "Gioca mentre aspetti una risposta 🐾",
        "tetris": "🧱 Gattetris", "lines": "Linee",
        "tetris_hint": "←→↓ — muovi · ↑ — ruota · Spazio — giù · P — pausa",
        "mines": "💣 Campo minato",
        "mines_hint": "Clic sx — apri · clic dx — bandierina · R — nuova partita",
        "win": "Hai vinto!", "lose": "Hai perso", "draw": "Pareggio",
        "cards": "🃏 Guerra", "card_ranks": "6 7 8 9 10 J Q K A",
        "cards_you": "Tu", "cards_cat": "Gatto",
        "cards_move": "Clic o Spazio — turno successivo",
        "cards_war": "⚔️ Guerra! Le carte restano sul tavolo",
        "mario": "🐱 Super Gatto", "lives": "Vite", "coins": "Monete",
        "mario_hint": "←→ — corri · ↑ / Spazio — salta · salta sui topi!",
        "kart": "🏎 Gatto-Kart", "lap": "Giro", "place": "Posizione",
        "kart_hint": "↑ — gas · ←→ — sterzo · ↓ — freno",
        "arka": "🧱 Gattanoide",
        "arka_hint": "Mouse / ←→ — racchetta · non far cadere la palla",
        "g15": "🧩 Gioco del 15", "moves": "Mosse", "solved": "Risolto!",
        "pairs": "🎴 Trova le coppie",
        "xo": "⭕ Tris", "xo_you": "Tocca a te", "xo_cat": "Tocca al gatto",
        "chess": "♞ Scacchi", "checkers": "Dama", "turn_white": "Tocca ai bianchi",
        "tanks": "▮ Carri", "gsearch": "Ricerca globale", "media_search": "Media della chat",
        "translate_chat": "Traduci la chat", "translating": "Traduzione…",
        "gs_hint": "Cerca in tutte le chat e i messaggi",
        "gs_chats": "Chat", "gs_msgs": "Messaggi",
        "cat_photos": "📷 Foto", "cat_videos": "🎬 Video", "cat_links": "🔗 Link",
        "cat_music": "🎵 Musica", "cat_contacts": "👤 Contatti",
        "wp_fish": "Pesci 🐟", "wp_hearts": "Cuori 💕",
        "ctx_copy": "Copia testo", "ctx_reply": "Rispondi", "ctx_fwd": "Inoltra",
        "ctx_del": "Elimina", "ctx_pin": "Fissa", "fwd_pick": "Inoltra a…",
        "fwd_ok": "Inoltrato", "pin_ok": "Fissato", "del_ok": "Eliminato",
        "replying": "Risposta al messaggio", "profile": "Profilo",
        "info_user": "Nome utente", "info_phone": "Telefono", "info_about": "Bio",
        "day_today": "Oggi",
        "set_trlang": "Lingua di traduzione", "tr_input": "Traduci ciò che scrivi",
        "set_device": "Dispositivo (client)", "dev_desktop": "Computer (CatGram)",
        "dev_android": "Android (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "Applicato dopo il riavvio", "set_notify": "Notifiche nel vassoio",
        "set_nsound": "Suono delle notifiche",
        "set_stream": "Video in streaming (senza scaricare)",
        "wp_file": "Dal computer 📁", "set_wall_pick": "Scegli file…",
        "play_app": "Gioca (mini-app del bot)",
        "not_bot": "Non è un bot: le mini-app stanno solo nei bot",
        "set_catcursor": "Cursore gattino con stecco 🐱",
        "turn_black": "Tocca ai neri", "in_check": "Scacco!",
        "white_wins": "Vincono i bianchi!", "black_wins": "Vincono i neri!",
        "stalemate": "Stallo — patta", "must_capture": "Presa obbligatoria!",
        "xo_win": "Hai vinto!", "xo_lose": "Ha vinto il gatto",
        "stickers": "Sticker", "st_load": "Carico gli sticker…",
        "st_none": "Nessun pacchetto di sticker",
        "st_fail": "Impossibile caricare le anteprime",
        "st_webp": "Questa build di Qt non legge WebP — gli sticker non si vedranno. "
                   "Installa dwebp (pacchetto libwebp-tools), ffmpeg o ImageMagick",
        "call": "Chiama su Telegram", "call_tel": "Chiama il numero (tel:)",
        "call_title": "Chiamata",
        "call_need_lib": "Le chiamate richiedono la libreria ntgcalls.<br>"
                         "Installa: <code>pip install ntgcalls</code>",
        "call_no_audio": "Nessun microfono o altoparlante trovato",
        "call_hint_throw": "Impossibile ottenere l'elenco dei dispositivi audio: {err}",
        "call_hint_libs": "Librerie audio di sistema non trovate. Installale e riavvia "
                           "catgram:\nDebian/Ubuntu: sudo apt install libpulse0 libasound2\n"
                           "Fedora: sudo dnf install pulseaudio-libs alsa-lib\n"
                           "Arch: sudo pacman -S libpulse alsa-lib\n"
                           "Verifica nel terminale: ldconfig -p | grep libpulse",
        "call_hint_server": "Il server audio (PulseAudio/PipeWire) non è raggiungibile "
                            "da questa sessione. Avvia catgram da un normale terminale "
                            "del desktop (non via SSH, non con sudo) e verifica che "
                            "l'audio funzioni.",
        "call_hint_pactl": "Il server audio sembra attivo, ma ntgcalls non vede "
                           "dispositivi. Esegui nello stesso terminale: pactl list short — "
                           "e invia l'output allo sviluppatore.",
        "call_hint_mic": "Nessun microfono visibile (gli altoparlanti ci sono). Collega "
                         "un microfono o abilitalo nelle impostazioni audio di sistema.",
        "call_hint_spk": "Nessun altoparlante visibile (c'è un microfono). Controlla i "
                         "dispositivi di output nelle impostazioni audio di sistema.",
        "call_bad_lib": "L'ntgcalls {ver} installata non va bene: manca {missing}.<br>"
                        "Prova <code>pip install -U ntgcalls</code> (nello stesso ambiente "
                        "in cui gira catgram). Se non basta, invia questo testo allo "
                        "sviluppatore:<br>{have}",
        "call_busy": "C'è già un'altra chiamata in corso",
        "call_no_phone": "Il numero di telefono non è visibile (privacy)",
        "call_people_only": "Si può chiamare solo le chat con persone",
        "call_tel_fail": "Nessuna app gestisce i link tel:. Installane una (es. KDE "
                         "Connect / GSConnect) o componi il numero a mano.",
        "call_dialing": "Chiamo…", "call_incoming": "Chiamata in arrivo…",
        "call_connecting": "Connessione…", "call_talking": "In chiamata",
        "call_accept": "Rispondi", "call_decline": "Rifiuta", "call_end": "Termina",
        "call_mute": "Silenzia il microfono", "call_unmute": "Riattiva il microfono",
        "call_ended": "Chiamata terminata", "call_missed": "Nessuna risposta",
        "call_peer_busy": "Rifiutata o occupata", "call_failed": "Connessione persa",
    },
    "pt": {
        "title": "🐱 catgram", "login": "🐱 catgram — entrar",
        "api_id": "api_id (my.telegram.org → API development tools):",
        "api_hash": "api_hash:",
        "phone": "Número de telefone (+código do país e número):",
        "bad_phone": "Número inválido. Use o formato internacional: "
                     "+<código do país><número> (sem 0 inicial), ex. +12025550123",
        "code": "Código do Telegram:", "bad_code": "Código errado, tente de novo:",
        "pw": "Senha da verificação em duas etapas:",
        "bad_pw": "Senha errada, mais uma vez:",
        "write": "Miau… escreva uma mensagem e pressione Enter",
        "find_chats": "Procurar conversas…",
        "find_msgs": "Procurar neste chat… (Enter — buscar, Esc — fechar)",
        "pick_chat": "Escolha um chat à esquerda", "menu": "catgram",
        "settings": "Configurações…", "accounts": "Contas…", "search": "Buscar no chat",
        "updates": "Verificar atualizações", "quit": "Sair", "me": "Eu",
        "m_sticker": "[figurinha]", "m_photo": "[foto]", "m_voice": "[áudio]",
        "m_video": "[vídeo]", "m_file": "[arquivo]", "m_other": "[anexo]",
        "set_title": "Configurações", "set_lang": "Idioma", "set_theme": "Tema",
        "theme_dark": "Escuro", "theme_light": "Claro", "set_font": "Tamanho da fonte",
        "set_avatars": "Avatares", "av_real": "Fotos reais (gato se não houver)",
        "av_cats": "Só gatos", "av_none": "Sem avatares",
        "set_photos": "Mostrar imagens no chat",
        "set_noise": "Supressão de ruído nas chamadas",
        "set_wallpaper": "Papel de parede do chat", "wp_none": "Nenhum", "wp_paws": "Patinhas 🐾",
        "wp_stars": "Estrelas ✨",
        "noise_off": "Supressão de ruído indisponível",
        "noise_on": "Supressão de ruído: {name}", "test_noise": "Testar",
        "acc_add": "Adicionar conta", "acc_switch": "Trocar", "acc_remove": "Remover",
        "acc_del_q": "Remover a conta {name}?",
        "acc_switch_q": "Reiniciar o catgram e mudar para {name}?",
        "acc_limit": "Limite atingido: 100 contas adicionais",
        "info": "Informações do chat", "about": "Descrição",
        "username": "Nome de usuário", "phone_lbl": "Telefone", "members": "Membros",
        "set_upd_start": "Verificar atualizações ao iniciar",
        "set_upd_url": "Endereço de atualizações (https)",
        "upd_no_url": "Nenhum endereço de atualizações. Adicione nas Configurações.",
        "upd_latest": "Você tem a versão mais recente.", "upd_new": "Nova versão disponível",
        "upd_err": "Não foi possível verificar atualizações",
        "res": "Resultados da busca", "nothing": "Nada encontrado",
        "online": "ronronando", "offline": "não ronrona",
        "attach_video": "Enviar um vídeo", "pick_video": "Escolha um vídeo",
        "video_files": "Vídeo", "all_files": "Todos os arquivos",
        "sending_video": "Enviando vídeo",
        "hist_start": "· começo da conversa ·",
        "hist_loading": "Carregando histórico…", "error": "Erro",
        "games": "🎮 Jogos", "snake": "🐍 Cobrinha", "g2048": "🐾 2048",
        "emoji": "Emojis", "score": "Pontos", "best": "Recorde",
        "game_over": "Fim de jogo", "paused": "Pausa",
        "again": "Pressione R para jogar de novo",
        "game_hint": "Espaço — pausa · R — novo jogo",
        "wait_hint": "Jogue enquanto espera a resposta 🐾",
        "tetris": "🧱 Gatotris", "lines": "Linhas",
        "tetris_hint": "←→↓ — mover · ↑ — girar · Espaço — soltar · P — pausa",
        "mines": "💣 Campo minado",
        "mines_hint": "Clique esq. — abrir · clique dir. — bandeira · R — novo jogo",
        "win": "Você ganhou!", "lose": "Você perdeu", "draw": "Empate",
        "cards": "🃏 Guerra", "card_ranks": "6 7 8 9 10 J Q K A",
        "cards_you": "Você", "cards_cat": "Gato",
        "cards_move": "Clique ou Espaço — próxima rodada",
        "cards_war": "⚔️ Guerra! As cartas ficam na mesa",
        "mario": "🐱 Super Gato", "lives": "Vidas", "coins": "Moedas",
        "mario_hint": "←→ — correr · ↑ / Espaço — pular · pise nos ratos!",
        "kart": "🏎 Gato-Kart", "lap": "Volta", "place": "Posição",
        "kart_hint": "↑ — acelerar · ←→ — volante · ↓ — freio",
        "arka": "🧱 Gatanoide",
        "arka_hint": "Mouse / ←→ — raquete · não deixe a bola cair",
        "g15": "🧩 Quebra-cabeça do 15", "moves": "Movimentos", "solved": "Resolvido!",
        "pairs": "🎴 Encontre os pares",
        "xo": "⭕ Jogo da velha", "xo_you": "Sua vez", "xo_cat": "Vez do gato",
        "chess": "♞ Xadrez", "checkers": "Damas", "turn_white": "Vez das brancas",
        "tanks": "▮ Tanques", "gsearch": "Busca global", "media_search": "Mídia do chat",
        "translate_chat": "Traduzir o chat", "translating": "Traduzindo…",
        "gs_hint": "Busca em todos os chats e mensagens",
        "gs_chats": "Chats", "gs_msgs": "Mensagens",
        "cat_photos": "📷 Fotos", "cat_videos": "🎬 Vídeos", "cat_links": "🔗 Links",
        "cat_music": "🎵 Música", "cat_contacts": "👤 Contatos",
        "wp_fish": "Peixes 🐟", "wp_hearts": "Corações 💕",
        "ctx_copy": "Copiar texto", "ctx_reply": "Responder", "ctx_fwd": "Encaminhar",
        "ctx_del": "Excluir", "ctx_pin": "Fixar", "fwd_pick": "Encaminhar para…",
        "fwd_ok": "Encaminhado", "pin_ok": "Fixado", "del_ok": "Excluído",
        "replying": "Responder à mensagem", "profile": "Perfil",
        "info_user": "Usuário", "info_phone": "Telefone", "info_about": "Bio",
        "day_today": "Hoje",
        "set_trlang": "Idioma de tradução", "tr_input": "Traduza o que você escreve",
        "set_device": "Dispositivo (cliente)", "dev_desktop": "Computador (CatGram)",
        "dev_android": "Android (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "Aplicado após reiniciar",
        "set_notify": "Notificações na bandeja", "set_nsound": "Som das notificações",
        "set_stream": "Vídeo em streaming (sem download)",
        "wp_file": "Do computador 📁", "set_wall_pick": "Escolher ficheiro…",
        "play_app": "Jogar (mini-app do bot)",
        "not_bot": "Não é um bot: mini-apps só existem em bots",
        "set_catcursor": "Cursor gatinho com palito 🐱",
        "turn_black": "Vez das pretas", "in_check": "Xeque!",
        "white_wins": "As brancas venceram!", "black_wins": "As pretas venceram!",
        "stalemate": "Afogamento — empate", "must_capture": "Captura obrigatória!",
        "xo_win": "Você ganhou!", "xo_lose": "O gato ganhou",
        "stickers": "Figurinhas", "st_load": "Carregando figurinhas…",
        "st_none": "Nenhum pacote de figurinhas",
        "st_fail": "Não foi possível carregar as prévias",
        "st_webp": "Essa compilação do Qt não lê WebP — as figurinhas não vão aparecer. "
                   "Instale dwebp (pacote libwebp-tools), ffmpeg ou ImageMagick",
        "call": "Ligar pelo Telegram", "call_tel": "Ligar para o número (tel:)",
        "call_title": "Chamada",
        "call_need_lib": "As chamadas precisam da biblioteca ntgcalls.<br>"
                         "Instale: <code>pip install ntgcalls</code>",
        "call_no_audio": "Nenhum microfone ou alto-falante encontrado",
        "call_hint_throw": "Não foi possível obter a lista de dispositivos de áudio: {err}",
        "call_hint_libs": "Bibliotecas de som do sistema não encontradas. Instale-as e "
                           "reinicie o catgram:\nDebian/Ubuntu: sudo apt install libpulse0 "
                           "libasound2\nFedora: sudo dnf install pulseaudio-libs alsa-lib\n"
                           "Arch: sudo pacman -S libpulse alsa-lib\n"
                           "Verifique no terminal: ldconfig -p | grep libpulse",
        "call_hint_server": "O servidor de som (PulseAudio/PipeWire) não é acessível "
                            "desta sessão. Inicie o catgram de um terminal normal do "
                            "desktop (não por SSH, não com sudo) e verifique se o som "
                            "funciona.",
        "call_hint_pactl": "O servidor de som parece funcionar, mas o ntgcalls não vê "
                           "dispositivos. Execute no mesmo terminal: pactl list short — "
                           "e envie a saída ao desenvolvedor.",
        "call_hint_mic": "Nenhum microfone visível (alto-falantes foram encontrados). "
                         "Conecte um microfone ou ative-o nas configurações de som.",
        "call_hint_spk": "Nenhum alto-falante visível (um microfone foi encontrado). "
                         "Verifique os dispositivos de saída nas configurações de som.",
        "call_bad_lib": "O ntgcalls {ver} instalado não serve: falta {missing}.<br>"
                        "Tente <code>pip install -U ntgcalls</code> (no mesmo ambiente em "
                        "que o catgram roda). Se não ajudar, envie este texto ao "
                        "desenvolvedor:<br>{have}",
        "call_busy": "Já há outra chamada em andamento",
        "call_no_phone": "O número de telefone não está visível (privacidade)",
        "call_people_only": "Só é possível ligar para conversas com pessoas",
        "call_tel_fail": "Nenhum app abre links tel:. Instale um (ex. KDE Connect / "
                         "GSConnect) ou disque o número manualmente.",
        "call_dialing": "Chamando…", "call_incoming": "Chamada recebida…",
        "call_connecting": "Conectando…", "call_talking": "Em chamada",
        "call_accept": "Aceitar", "call_decline": "Recusar", "call_end": "Encerrar",
        "call_mute": "Silenciar microfone", "call_unmute": "Ativar microfone",
        "call_ended": "Chamada encerrada", "call_missed": "Sem resposta",
        "call_peer_busy": "Recusada ou ocupada", "call_failed": "Conexão perdida",
    },
    "pl": {
        "title": "🐱 catgram", "login": "🐱 catgram — logowanie",
        "api_id": "api_id (my.telegram.org → API development tools):",
        "api_hash": "api_hash:",
        "phone": "Numer telefonu (+kod kraju i numer):",
        "bad_phone": "Nieprawidłowy numer. Użyj formatu międzynarodowego: "
                     "+<kod kraju><numer> (bez zer z przodu), np. +12025550123",
        "code": "Kod z Telegrama:", "bad_code": "Zły kod, spróbuj jeszcze raz:",
        "pw": "Hasło weryfikacji dwuetapowej:",
        "bad_pw": "Złe hasło, jeszcze raz:",
        "write": "Miau… napisz wiadomość i naciśnij Enter",
        "find_chats": "Szukaj czatów…",
        "find_msgs": "Szukaj w tym czacie… (Enter — szukaj, Esc — zamknij)",
        "pick_chat": "Wybierz czat po lewej", "menu": "catgram",
        "settings": "Ustawienia…", "accounts": "Konta…", "search": "Szukaj w czacie",
        "updates": "Sprawdź aktualizacje", "quit": "Zakończ", "me": "Ja",
        "m_sticker": "[naklejka]", "m_photo": "[zdjęcie]", "m_voice": "[wiadomość głosowa]",
        "m_video": "[wideo]", "m_file": "[plik]", "m_other": "[załącznik]",
        "set_title": "Ustawienia", "set_lang": "Język", "set_theme": "Motyw",
        "theme_dark": "Ciemny", "theme_light": "Jasny", "set_font": "Rozmiar czcionki",
        "set_avatars": "Avatary", "av_real": "Prawdziwe zdjęcia (kot, jeśli brak)",
        "av_cats": "Tylko koty", "av_none": "Bez avatarów",
        "set_photos": "Pokazuj obrazki na czacie",
        "set_noise": "Tłumienie szumów w rozmowach",
        "set_wallpaper": "Tapeta czatu", "wp_none": "Brak", "wp_paws": "Łapki 🐾",
        "wp_stars": "Gwiazdki ✨",
        "noise_off": "Tłumienie szumów niedostępne",
        "noise_on": "Tłumienie szumów: {name}", "test_noise": "Testuj",
        "acc_add": "Dodaj konto", "acc_switch": "Przełącz", "acc_remove": "Usuń",
        "acc_del_q": "Usunąć konto {name}?",
        "acc_switch_q": "Zrestartować catgram i przełączyć na {name}?",
        "acc_limit": "Osiągnięto limit: 100 dodatkowych kont",
        "info": "Informacje o czacie", "about": "Opis",
        "username": "Nazwa użytkownika", "phone_lbl": "Telefon", "members": "Uczestników",
        "set_upd_start": "Sprawdzaj aktualizacje przy starcie",
        "set_upd_url": "Adres aktualizacji (https)",
        "upd_no_url": "Brak adresu aktualizacji. Podaj go w ustawieniach.",
        "upd_latest": "Masz najnowszą wersję.", "upd_new": "Dostępna nowa wersja",
        "upd_err": "Nie udało się sprawdzić aktualizacji",
        "res": "Wyniki wyszukiwania", "nothing": "Nic nie znaleziono",
        "online": "mruczy", "offline": "nie mruczy",
        "attach_video": "Wyślij wideo", "pick_video": "Wybierz wideo",
        "video_files": "Wideo", "all_files": "Wszystkie pliki",
        "sending_video": "Wysyłam wideo",
        "hist_start": "· początek rozmowy ·",
        "hist_loading": "Wczytuję historię…", "error": "Błąd",
        "games": "🎮 Gry", "snake": "🐍 Wężyk", "g2048": "🐾 2048",
        "emoji": "Emocjiki", "score": "Wynik", "best": "Rekord",
        "game_over": "Koniec gry", "paused": "Pauza",
        "again": "Naciśnij R, aby zagrać ponownie",
        "game_hint": "Spacja — pauza · R — nowa gra",
        "wait_hint": "Zagraj, czekając na odpowiedź 🐾",
        "tetris": "🧱 Kotetris", "lines": "Linie",
        "tetris_hint": "←→↓ — ruch · ↑ — obrót · Spacja — zrzut · P — pauza",
        "mines": "💣 Saper",
        "mines_hint": "LPM — otwórz · PPM — flaga · R — nowa gra",
        "win": "Wygrywasz!", "lose": "Przegrywasz", "draw": "Remis",
        "cards": "🃏 Wojna", "card_ranks": "6 7 8 9 10 W D K A",
        "cards_you": "Ty", "cards_cat": "Kot",
        "cards_move": "Klik lub Spacja — następna runda",
        "cards_war": "⚔️ Wojna! Karty zostają na stole",
        "mario": "🐱 Super Kot", "lives": "Życia", "coins": "Monety",
        "mario_hint": "←→ — bieg · ↑ / Spacja — skok · skacz na myszy!",
        "kart": "🏎 Kotokart", "lap": "Okrążenie", "place": "Miejsce",
        "kart_hint": "↑ — gaz · ←→ — kierownica · ↓ — hamulec",
        "arka": "🧱 Kotanoid",
        "arka_hint": "Mysz / ←→ — paletka · nie upuść piłki",
        "g15": "🧩 Piętnastka", "moves": "Ruchy", "solved": "Ułożone!",
        "pairs": "🎴 Znajdź pary",
        "xo": "⭕ Kółko i krzyżyk", "xo_you": "Twój ruch", "xo_cat": "Ruch kota",
        "chess": "♞ Szachy", "checkers": "Warcaby", "turn_white": "Ruch białych",
        "tanks": "▮ Czołgi", "gsearch": "Wyszukiwanie globalne", "media_search": "Multimedia czatu",
        "translate_chat": "Przetłumacz czat", "translating": "Tłumaczenie…",
        "gs_hint": "Szukaj we wszystkich czatach i wiadomościach",
        "gs_chats": "Czaty", "gs_msgs": "Wiadomości",
        "cat_photos": "📷 Zdjęcia", "cat_videos": "🎬 Filmy", "cat_links": "🔗 Linki",
        "cat_music": "🎵 Muzyka", "cat_contacts": "👤 Kontakty",
        "wp_fish": "Rybki 🐟", "wp_hearts": "Serduszka 💕",
        "ctx_copy": "Kopiuj tekst", "ctx_reply": "Odpowiedz", "ctx_fwd": "Przekaż",
        "ctx_del": "Usuń", "ctx_pin": "Przypnij", "fwd_pick": "Przekaż do…",
        "fwd_ok": "Przekazano", "pin_ok": "Przypięto", "del_ok": "Usunięto",
        "replying": "Odpowiedź na wiadomość", "profile": "Profil",
        "info_user": "Nazwa użytkownika", "info_phone": "Telefon", "info_about": "O mnie",
        "day_today": "Dzisiaj",
        "set_trlang": "Język tłumaczenia", "tr_input": "Przetłumacz to, co piszesz",
        "set_device": "Urządzenie (klient)", "dev_desktop": "Komputer (CatGram)",
        "dev_android": "Android (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "Zadziała po restarcie", "set_notify": "Powiadomienia w zasobniku",
        "set_nsound": "Dźwięk powiadomień", "set_stream": "Wideo bez pobierania (strumień)",
        "wp_file": "Z komputera 📁", "set_wall_pick": "Wybierz plik…",
        "play_app": "Graj (mini-apka bota)",
        "not_bot": "To nie bot: mini-apki mają tylko boty",
        "set_catcursor": "Kursor-kotek z patyczkiem 🐱",
        "turn_black": "Ruch czarnych", "in_check": "Szach!",
        "white_wins": "Białe wygrywają!", "black_wins": "Czarne wygrywają!",
        "stalemate": "Pat — remis", "must_capture": "Bicie obowiązkowe!",
        "xo_win": "Wygrałeś!", "xo_lose": "Wygrał kot",
        "stickers": "Naklejki", "st_load": "Wczytuję naklejki…",
        "st_none": "Brak pakietów naklejek",
        "st_fail": "Nie udało się wczytać miniatur",
        "st_webp": "Ta kompilacja Qt nie czyta WebP — naklejki się nie pokażą. "
                   "Zainstaluj dwebp (pakiet libwebp-tools), ffmpeg lub ImageMagick",
        "call": "Zadzwoń przez Telegram", "call_tel": "Zadzwoń na numer (tel:)",
        "call_title": "Rozmowa",
        "call_need_lib": "Rozmowy wymagają biblioteki ntgcalls.<br>"
                         "Zainstaluj: <code>pip install ntgcalls</code>",
        "call_no_audio": "Nie znaleziono mikrofonu ani głośników",
        "call_hint_throw": "Nie udało się pobrać listy urządzeń audio: {err}",
        "call_hint_libs": "Nie znaleziono systemowych bibliotek dźwięku. Zainstaluj je "
                          "i zrestartuj catgram:\nDebian/Ubuntu: sudo apt install "
                          "libpulse0 libasound2\nFedora: sudo dnf install pulseaudio-libs "
                          "alsa-lib\nArch: sudo pacman -S libpulse alsa-lib\n"
                          "Sprawdź w terminalu: ldconfig -p | grep libpulse",
        "call_hint_server": "Serwer dźwięku (PulseAudio/PipeWire) jest niedostępny z tej "
                            "sesji. Uruchom catgram ze zwykłego terminala pulpitu (nie "
                            "przez SSH, nie przez sudo) i sprawdź, czy dźwięk działa.",
        "call_hint_pactl": "Serwer dźwięku działa, ale ntgcalls nie widzi urządzeń. "
                           "Wykonaj w tym samym terminalu: pactl list short — i wyślij "
                           "wyjście deweloperowi.",
        "call_hint_mic": "Nie widać mikrofonu (głośniki się znalazły). Podłącz mikrofon "
                         "lub włącz go w ustawieniach dźwięku systemu.",
        "call_hint_spk": "Nie widać głośników (znaleziono mikrofon). Sprawdź urządzenia "
                         "wyjściowe w ustawieniach dźwięku systemu.",
        "call_bad_lib": "Zainstalowane ntgcalls {ver} nie pasuje: brakuje {missing}.<br>"
                        "Spróbuj <code>pip install -U ntgcalls</code> (w tym samym "
                        "środowisku, w którym działa catgram). Jeśli nie pomoże, wyślij ten "
                        "tekst deweloperowi:<br>{have}",
        "call_busy": "Trwa już inna rozmowa",
        "call_no_phone": "Numer telefonu niewidoczny (ustawienia prywatności)",
        "call_people_only": "Dzwonić można tylko w czatach z ludźmi",
        "call_tel_fail": "Żadna aplikacja nie otwiera linków tel:. Zainstaluj taką "
                         "(np. KDE Connect / GSConnect) albo wybierz numer ręcznie.",
        "call_dialing": "Dzwonię…", "call_incoming": "Połączenie przychodzące…",
        "call_connecting": "Łączę…", "call_talking": "W rozmowie",
        "call_accept": "Odbierz", "call_decline": "Odrzuć", "call_end": "Zakończ",
        "call_mute": "Wycisz mikrofon", "call_unmute": "Włącz mikrofon",
        "call_ended": "Rozmowa zakończona", "call_missed": "Brak odpowiedzi",
        "call_peer_busy": "Odrzucone lub zajęte", "call_failed": "Połączenie zerwane",
    },
    "tr": {
        "title": "🐱 catgram", "login": "🐱 catgram — giriş",
        "api_id": "api_id (my.telegram.org → API development tools):",
        "api_hash": "api_hash:",
        "phone": "Telefon numarası (+ülke kodu ve numara):",
        "bad_phone": "Numara geçersiz. Uluslararası biçim kullanın: "
                     "+<ülke kodu><numara> (baştaki 0 olmadan), örn. +12025550123",
        "code": "Telegram'dan gelen kod:", "bad_code": "Kod yanlış, tekrar deneyin:",
        "pw": "İki adımlı doğrulama şifresi:",
        "bad_pw": "Şifre yanlış, tekrar:",
        "write": "Miyav… bir mesaj yazın ve Enter'a basın",
        "find_chats": "Sohbet ara…",
        "find_msgs": "Bu sohbette ara… (Enter — ara, Esc — kapat)",
        "pick_chat": "Soldan bir sohbet seçin", "menu": "catgram",
        "settings": "Ayarlar…", "accounts": "Hesaplar…", "search": "Sohbette ara",
        "updates": "Güncellemeleri kontrol et", "quit": "Çıkış", "me": "Ben",
        "m_sticker": "[çıkartma]", "m_photo": "[fotoğraf]", "m_voice": "[sesli]",
        "m_video": "[video]", "m_file": "[dosya]", "m_other": "[ek]",
        "set_title": "Ayarlar", "set_lang": "Dil", "set_theme": "Tema",
        "theme_dark": "Koyu", "theme_light": "Açık", "set_font": "Yazı boyutu",
        "set_avatars": "Avatarlar", "av_real": "Gerçek fotoğraflar (yoksa kedi)",
        "av_cats": "Sadece kediler", "av_none": "Avatar yok",
        "set_photos": "Sohbette resimleri göster",
        "set_noise": "Aramalarda gürültü bastırma",
        "set_wallpaper": "Sohbet duvar kağıdı", "wp_none": "Yok", "wp_paws": "Pati 🐾",
        "wp_stars": "Yıldızlar ✨",
        "noise_off": "Gürültü bastırma kullanılamıyor",
        "noise_on": "Gürültü bastırma: {name}", "test_noise": "Test et",
        "acc_add": "Hesap ekle", "acc_switch": "Geç", "acc_remove": "Kaldır",
        "acc_del_q": "{name} hesabı kaldırılsın mı?",
        "acc_switch_q": "catgram yeniden başlatılıp {name} hesabına geçilsin mi?",
        "acc_limit": "Sınıra ulaşıldı: 100 ek hesap",
        "info": "Sohbet bilgisi", "about": "Açıklama",
        "username": "Kullanıcı adı", "phone_lbl": "Telefon", "members": "Üye",
        "set_upd_start": "Açılışta güncellemeleri kontrol et",
        "set_upd_url": "Güncelleme adresi (https)",
        "upd_no_url": "Güncelleme adresi yok. Ayarlardan ekleyin.",
        "upd_latest": "En son sürüme sahipsiniz.", "upd_new": "Yeni sürüm var",
        "upd_err": "Güncellemeler kontrol edilemedi",
        "res": "Arama sonuçları", "nothing": "Hiçbir şey bulunamadı",
        "online": "mırıldıyor", "offline": "mırıldamıyor",
        "attach_video": "Video gönder", "pick_video": "Video seçin",
        "video_files": "Video", "all_files": "Tüm dosyalar",
        "sending_video": "Video gönderiliyor",
        "hist_start": "· sohbetin başı ·",
        "hist_loading": "Geçmiş yükleniyor…", "error": "Hata",
        "games": "🎮 Oyunlar", "snake": "🐍 Yılan", "g2048": "🐾 2048",
        "emoji": "Emojiler", "score": "Puan", "best": "Rekor",
        "game_over": "Oyun bitti", "paused": "Duraklatıldı",
        "again": "Tekrar oynamak için R'ye basın",
        "game_hint": "Boşluk — durdur · R — yeni oyun",
        "wait_hint": "Cevabı beklerken oynayın 🐾",
        "tetris": "🧱 Keditris", "lines": "Satır",
        "tetris_hint": "←→↓ — hareket · ↑ — döndür · Boşluk — bırak · P — durdur",
        "mines": "💣 Mayın tarlası",
        "mines_hint": "Sol tık — aç · sağ tık — bayrak · R — yeni oyun",
        "win": "Kazandın!", "lose": "Kaybettin", "draw": "Berabere",
        "cards": "🃏 Savaş", "card_ranks": "6 7 8 9 10 J Q K A",
        "cards_you": "Sen", "cards_cat": "Kedi",
        "cards_move": "Tık veya Boşluk — sonraki tur",
        "cards_war": "⚔️ Savaş! Kartlar masada kalıyor",
        "mario": "🐱 Süper Kedi", "lives": "Can", "coins": "Altın",
        "mario_hint": "←→ — koş · ↑ / Boşluk — zıpla · farelerin üstüne atla!",
        "kart": "🏎 Kedi-Kart", "lap": "Tur", "place": "Sıra",
        "kart_hint": "↑ — gaz · ←→ — direksiyon · ↓ — fren",
        "arka": "🧱 Kedinoid",
        "arka_hint": "Fare / ←→ — raket · topu düşürmeyin",
        "g15": "🧩 15 bulmaca", "moves": "Hamle", "solved": "Çözüldü!",
        "pairs": "🎴 Eşleri bul",
        "xo": "⭕ XOX", "xo_you": "Sıra sende", "xo_cat": "Kedinin sırası",
        "chess": "♞ Satranç", "checkers": "Dama", "turn_white": "Beyazların sırası",
        "tanks": "▮ Tanklar", "gsearch": "Genel arama", "media_search": "Sohbet medyası",
        "translate_chat": "Sohbeti çevir", "translating": "Çevriliyor…",
        "gs_hint": "Tüm sohbet ve mesajlarda ara",
        "gs_chats": "Sohbetler", "gs_msgs": "Mesajlar",
        "cat_photos": "📷 Fotoğraflar", "cat_videos": "🎬 Videolar", "cat_links": "🔗 Bağlantılar",
        "cat_music": "🎵 Müzik", "cat_contacts": "👤 Kişiler",
        "wp_fish": "Balıklar 🐟", "wp_hearts": "Kalpler 💕",
        "ctx_copy": "Metni kopyala", "ctx_reply": "Yanıtla", "ctx_fwd": "İlet",
        "ctx_del": "Sil", "ctx_pin": "Sabitle", "fwd_pick": "Şuraya ilet…",
        "fwd_ok": "İletildi", "pin_ok": "Sabitlendi", "del_ok": "Silindi",
        "replying": "Mesajı yanıtla", "profile": "Profil",
        "info_user": "Kullanıcı adı", "info_phone": "Telefon", "info_about": "Hakkında",
        "day_today": "Bugün",
        "set_trlang": "Çeviri dili", "tr_input": "Yazdığını çevir",
        "set_device": "Cihaz (istemci)", "dev_desktop": "Bilgisayar (CatGram)",
        "dev_android": "Android (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "Yeniden başlatınca uygulanır", "set_notify": "Tepsi bildirimleri",
        "set_nsound": "Bildirim sesi", "set_stream": "Video akışı (indirmeden)",
        "wp_file": "Bilgisayardan 📁", "set_wall_pick": "Dosya seç…",
        "play_app": "Oyna (botun mini uygulaması)",
        "not_bot": "Bu bir bot değil: mini uygulamalar yalnızca botlarda olur",
        "set_catcursor": "Çubuklu kedi imleci 🐱",
        "turn_black": "Siyahların sırası", "in_check": "Şah!",
        "white_wins": "Beyazlar kazandı!", "black_wins": "Siyahlar kazandı!",
        "stalemate": "Pat — berabere", "must_capture": "Zorunlu alma!",
        "xo_win": "Kazandın!", "xo_lose": "Kedi kazandı",
        "stickers": "Çıkartmalar", "st_load": "Çıkartmalar yükleniyor…",
        "st_none": "Çıkartma seti yok", "st_fail": "Önizlemeler yüklenemedi",
        "st_webp": "Bu Qt derlemesi WebP okuyamıyor — çıkartmalar görünmez. dwebp "
                   "(libwebp-tools paketi), ffmpeg veya ImageMagick kurun",
        "call": "Telegram'dan ara", "call_tel": "Numarayı ara (tel:)",
        "call_title": "Arama",
        "call_need_lib": "Aramalar için ntgcalls kütüphanesi gerekir.<br>"
                         "Kurun: <code>pip install ntgcalls</code>",
        "call_no_audio": "Mikrofon veya hoparlör bulunamadı",
        "call_hint_throw": "Ses aygıtı listesi alınamadı: {err}",
        "call_hint_libs": "Sistem ses kütüphaneleri bulunamadı. Kurun ve catgram'ı "
                          "yeniden başlatın:\nDebian/Ubuntu: sudo apt install libpulse0 "
                          "libasound2\nFedora: sudo dnf install pulseaudio-libs alsa-lib\n"
                          "Arch: sudo pacman -S libpulse alsa-lib\n"
                          "Terminalde kontrol: ldconfig -p | grep libpulse",
        "call_hint_server": "Ses sunucusu (PulseAudio/PipeWire) bu oturumdan erişilemiyor. "
                            "catgram'ı normal masaüstü terminalinden başlatın (SSH ile "
                            "değil, sudo ile değil) ve sesin çalıştığından emin olun.",
        "call_hint_pactl": "Ses sunucusu çalışıyor gibi görünüyor ama ntgcalls aygıt "
                           "görmüyor. Aynı terminalde çalıştırın: pactl list short — ve "
                           "çıktıyı geliştiriciye gönderin.",
        "call_hint_mic": "Mikrofon görünmüyor (hoparlörler bulundu). Mikrofon takın veya "
                         "sistem ses ayarlarından etkinleştirin.",
        "call_hint_spk": "Hoparlör görünmüyor (mikrofon bulundu). Sistem ses ayarlarından "
                        "çıktı aygıtlarını kontrol edin.",
        "call_bad_lib": "Yüklü ntgcalls {ver} uygun değil: {missing} eksik.<br>"
                        "<code>pip install -U ntgcalls</code> deneyin (catgram'ın "
                        "çalıştığı ortamda). Olmazsa bu metni geliştiriciye gönderin:"
                        "<br>{have}",
        "call_busy": "Başka bir arama sürüyor",
        "call_no_phone": "Telefon numarası görünmüyor (gizlilik ayarları)",
        "call_people_only": "Arama yalnızca kişilerle yapılan sohbetlerde mümkün",
        "call_tel_fail": "tel: bağlantılarını açan uygulama yok. Bir tane kurun (örn. KDE "
                         "Connect / GSConnect) veya numarayı elle tuşlayın.",
        "call_dialing": "Aranıyor…", "call_incoming": "Gelen arama…",
        "call_connecting": "Bağlanıyor…", "call_talking": "Aramada",
        "call_accept": "Kabul et", "call_decline": "Reddet", "call_end": "Bitir",
        "call_mute": "Mikrofonu kapat", "call_unmute": "Mikrofonu aç",
        "call_ended": "Arama sona erdi", "call_missed": "Cevap yok",
        "call_peer_busy": "Reddedildi ya da meşgul", "call_failed": "Bağlantı koptu",
    },
    "zh": {
        "title": "🐱 catgram", "login": "🐱 catgram — 登录",
        "api_id": "api_id (my.telegram.org → API development tools):",
        "api_hash": "api_hash:",
        "phone": "电话号码（+国家码和号码）:",
        "bad_phone": "号码无效。请使用国际格式：+<国家码><号码>（开头不带 0），"
                     "例如 +12025550123",
        "code": "Telegram 发来的验证码:", "bad_code": "验证码错误，请重试:",
        "pw": "两步验证密码:", "bad_pw": "密码错误，再试一次:",
        "write": "喵…写一条消息并按回车",
        "find_chats": "搜索聊天…",
        "find_msgs": "在本聊天中搜索…（回车 — 搜索，Esc — 关闭）",
        "pick_chat": "在左侧选择一个聊天", "menu": "catgram",
        "settings": "设置…", "accounts": "账号…", "search": "在聊天中搜索",
        "updates": "检查更新", "quit": "退出", "me": "我",
        "m_sticker": "[贴纸]", "m_photo": "[图片]", "m_voice": "[语音]",
        "m_video": "[视频]", "m_file": "[文件]", "m_other": "[附件]",
        "set_title": "设置", "set_lang": "语言", "set_theme": "主题",
        "theme_dark": "深色", "theme_light": "浅色", "set_font": "字体大小",
        "set_avatars": "头像", "av_real": "真实照片（没有则显示猫）",
        "av_cats": "只用猫咪", "av_none": "无头像",
        "set_photos": "在聊天中显示图片",
        "set_noise": "通话时抑制噪音",
        "set_wallpaper": "聊天壁纸", "wp_none": "无", "wp_paws": "猫爪印 🐾",
        "wp_stars": "星星 ✨",
        "noise_off": "噪音抑制不可用",
        "noise_on": "噪音抑制：{name}", "test_noise": "测试",
        "acc_add": "添加账号", "acc_switch": "切换", "acc_remove": "删除",
        "acc_del_q": "删除账号 {name}？",
        "acc_switch_q": "重启 catgram 并切换到 {name}？",
        "acc_limit": "已达上限：100 个额外账号",
        "info": "聊天信息", "about": "简介",
        "username": "用户名", "phone_lbl": "电话", "members": "成员",
        "set_upd_start": "启动时检查更新", "set_upd_url": "更新地址 (https)",
        "upd_no_url": "未设置更新地址。请在设置中添加。",
        "upd_latest": "你已是最新版本。", "upd_new": "有新版本可用",
        "upd_err": "无法检查更新",
        "res": "搜索结果", "nothing": "什么也没找到",
        "online": "咕噜咕噜", "offline": "不咕噜了",
        "attach_video": "发送视频", "pick_video": "选择视频",
        "video_files": "视频", "all_files": "所有文件",
        "sending_video": "正在发送视频",
        "hist_start": "· 对话的开头 ·",
        "hist_loading": "正在加载历史记录…", "error": "错误",
        "games": "🎮 游戏", "snake": "🐍 贪吃蛇", "g2048": "🐾 2048",
        "emoji": "表情", "score": "得分", "best": "最高分",
        "game_over": "游戏结束", "paused": "已暂停",
        "again": "按 R 再来一局",
        "game_hint": "空格 — 暂停 · R — 新游戏",
        "wait_hint": "等回复的时候来玩一局 🐾",
        "tetris": "🧱 猫猫方块", "lines": "行数",
        "tetris_hint": "←→↓ — 移动 · ↑ — 旋转 · 空格 — 直落 · P — 暂停",
        "mines": "💣 扫雷",
        "mines_hint": "左键 — 打开 · 右键 — 插旗 · R — 新游戏",
        "win": "你赢了！", "lose": "你输了", "draw": "平局",
        "cards": "🃏 战争", "card_ranks": "6 7 8 9 10 J Q K A",
        "cards_you": "你", "cards_cat": "猫",
        "cards_move": "点击或空格 — 下一轮",
        "cards_war": "⚔️ 开战！牌留在桌上",
        "mario": "🐱 超级猫", "lives": "生命", "coins": "金币",
        "mario_hint": "←→ — 跑 · ↑ / 空格 — 跳 · 踩老鼠！",
        "kart": "🏎 猫猫卡丁车", "lap": "圈", "place": "名次",
        "kart_hint": "↑ — 油门 · ←→ — 方向 · ↓ — 刹车",
        "arka": "🧱 猫猫打砖块",
        "arka_hint": "鼠标 / ←→ — 挡板 · 别让球掉下去",
        "g15": "🧩 十五数字拼图", "moves": "步数", "solved": "完成！",
        "pairs": "🎴 找配对",
        "xo": "⭕ 井字棋", "xo_you": "轮到你", "xo_cat": "轮到猫",
        "chess": "♞ 国际象棋", "checkers": "国际跳棋", "turn_white": "轮到白棋",
        "tanks": "▮ 坦克", "gsearch": "全局搜索", "media_search": "聊天媒体",
        "translate_chat": "翻译聊天", "translating": "翻译中…",
        "gs_hint": "搜索所有聊天和消息",
        "gs_chats": "聊天", "gs_msgs": "消息",
        "cat_photos": "📷 照片", "cat_videos": "🎬 视频", "cat_links": "🔗 链接",
        "cat_music": "🎵 音乐", "cat_contacts": "👤 联系人",
        "wp_fish": "小鱼 🐟", "wp_hearts": "爱心 💕",
        "ctx_copy": "复制文本", "ctx_reply": "回复", "ctx_fwd": "转发",
        "ctx_del": "删除", "ctx_pin": "置顶", "fwd_pick": "转发到…",
        "fwd_ok": "已转发", "pin_ok": "已置顶", "del_ok": "已删除",
        "replying": "回复消息", "profile": "资料",
        "info_user": "用户名", "info_phone": "电话", "info_about": "简介",
        "day_today": "今天",
        "set_trlang": "翻译语言", "tr_input": "翻译所写内容",
        "set_device": "设备（客户端）", "dev_desktop": "电脑 (CatGram)",
        "dev_android": "安卓 (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "重启后生效", "set_notify": "托盘通知",
        "set_nsound": "通知声音", "set_stream": "视频边下边播（免下载）",
        "wp_file": "来自电脑 📁", "set_wall_pick": "选择文件…",
        "play_app": "玩（机器人小程序）",
        "not_bot": "这不是机器人：小程序只在机器人聊天里",
        "set_catcursor": "小猫棒子光标 🐱",
        "turn_black": "轮到黑棋", "in_check": "将军！", "white_wins": "白棋获胜！",
        "black_wins": "黑棋获胜！", "stalemate": "逼和 — 平局",
        "must_capture": "必须吃子！",
        "xo_win": "你赢了！", "xo_lose": "猫赢了",
        "stickers": "贴纸", "st_load": "正在加载贴纸…",
        "st_none": "没有贴纸包", "st_fail": "预览加载失败",
        "st_webp": "此 Qt 构建无法读取 WebP — 贴纸无法显示。请安装 dwebp"
                   "（libwebp-tools 软件包）、ffmpeg 或 ImageMagick",
        "call": "用 Telegram 通话", "call_tel": "拨打电话号码 (tel:)",
        "call_title": "通话",
        "call_need_lib": "通话需要 ntgcalls 库。<br>请安装: <code>pip install "
                         "ntgcalls</code>",
        "call_no_audio": "未找到麦克风或扬声器",
        "call_hint_throw": "无法获取音频设备列表: {err}",
        "call_hint_libs": "未找到系统音频库。请安装后重启 catgram:\nDebian/Ubuntu: "
                          "sudo apt install libpulse0 libasound2\nFedora: sudo dnf install "
                          "pulseaudio-libs alsa-lib\nArch: sudo pacman -S libpulse "
                          "alsa-lib\n在终端检查: ldconfig -p | grep libpulse",
        "call_hint_server": "无法从当前会话访问声音服务器 (PulseAudio/PipeWire)。请从"
                            "普通桌面终端启动 catgram（不要通过 SSH 或 sudo），并确认"
                            "系统声音正常。",
        "call_hint_pactl": "声音服务器似乎在运行，但 ntgcalls 看不到设备。请在同一"
                           "终端运行: pactl list short — 并把输出发给开发者。",
        "call_hint_mic": "看不到麦克风（找到了扬声器）。请插入麦克风，或在系统声音"
                         "设置中启用它。",
        "call_hint_spk": "看不到扬声器（找到了麦克风）。请在系统声音设置中检查输出"
                         "设备。",
        "call_bad_lib": "已安装的 ntgcalls {ver} 不合适: 缺少 {missing}。<br>请尝试 "
                        "<code>pip install -U ntgcalls</code>（在与 catgram 相同的"
                        "环境中）。若无效，请把这段文字发给开发者:<br>{have}",
        "call_busy": "已有另一通通话在进行",
        "call_no_phone": "看不到电话号码（隐私设置）",
        "call_people_only": "只能对与人的聊天发起通话",
        "call_tel_fail": "没有应用处理 tel: 链接。请安装一个（如 KDE Connect / "
                         "GSConnect）或手动拨号。",
        "call_dialing": "正在呼叫…", "call_incoming": "来电…",
        "call_connecting": "正在连接…", "call_talking": "通话中",
        "call_accept": "接听", "call_decline": "拒绝", "call_end": "挂断",
        "call_mute": "静音麦克风", "call_unmute": "取消静音",
        "call_ended": "通话已结束", "call_missed": "无人接听",
        "call_peer_busy": "被拒绝或占线", "call_failed": "连接丢失",
    },
    "ja": {
        "title": "🐱 catgram", "login": "🐱 catgram — ログイン",
        "api_id": "api_id (my.telegram.org → API development tools):",
        "api_hash": "api_hash:",
        "phone": "電話番号（+国コードと番号）:",
        "bad_phone": "番号が正しくありません。国際形式で入力してください: "
                     "+<国コード><番号>（先頭の 0 なし）、例 +12025550123",
        "code": "Telegram のコード:", "bad_code": "コードが違います。もう一度:",
        "pw": "二段階認証パスワード:", "bad_pw": "パスワードが違います。もう一度:",
        "write": "ニャ…メッセージを書いて Enter を押してください",
        "find_chats": "チャットを検索…",
        "find_msgs": "このチャット内を検索…（Enter — 検索、Esc — 閉じる）",
        "pick_chat": "左からチャットを選んでください", "menu": "catgram",
        "settings": "設定…", "accounts": "アカウント…", "search": "チャット内検索",
        "updates": "更新を確認", "quit": "終了", "me": "自分",
        "m_sticker": "[スタンプ]", "m_photo": "[写真]", "m_voice": "[ボイス]",
        "m_video": "[動画]", "m_file": "[ファイル]", "m_other": "[添付]",
        "set_title": "設定", "set_lang": "言語", "set_theme": "テーマ",
        "theme_dark": "ダーク", "theme_light": "ライト", "set_font": "文字サイズ",
        "set_avatars": "アバター", "av_real": "本物の写真（なければ猫）",
        "av_cats": "猫だけ", "av_none": "なし",
        "set_photos": "チャットに画像を表示",
        "set_noise": "通話中のノイズ抑制",
        "set_wallpaper": "チャットの壁紙", "wp_none": "なし", "wp_paws": "肉球 🐾",
        "wp_stars": "星 ✨",
        "noise_off": "ノイズ抑制は利用できません",
        "noise_on": "ノイズ抑制: {name}", "test_noise": "テスト",
        "acc_add": "アカウントを追加", "acc_switch": "切り替え", "acc_remove": "削除",
        "acc_del_q": "アカウント {name} を削除しますか？",
        "acc_switch_q": "catgram を再起動して {name} に切り替えますか？",
        "acc_limit": "上限に達しました: 追加アカウント 100 件",
        "info": "チャット情報", "about": "説明",
        "username": "ユーザー名", "phone_lbl": "電話", "members": "メンバー",
        "set_upd_start": "起動時に更新を確認",
        "set_upd_url": "更新 URL (https)",
        "upd_no_url": "更新 URL が設定されていません。設定で追加してください。",
        "upd_latest": "最新版です。", "upd_new": "新しいバージョンがあります",
        "upd_err": "更新を確認できませんでした",
        "res": "検索結果", "nothing": "何も見つかりません",
        "online": "ゴロゴロ中", "offline": "ゴロゴロしてない",
        "attach_video": "動画を送る", "pick_video": "動画を選択",
        "video_files": "動画", "all_files": "すべてのファイル",
        "sending_video": "動画を送信中",
        "hist_start": "· 会話の最初 ·",
        "hist_loading": "履歴を読み込み中…", "error": "エラー",
        "games": "🎮 ゲーム", "snake": "🐍 スネーク", "g2048": "🐾 2048",
        "emoji": "絵文字", "score": "スコア", "best": "ベスト",
        "game_over": "ゲームオーバー", "paused": "一時停止",
        "again": "R を押すともう一度",
        "game_hint": "スペース — 一時停止 · R — 新しいゲーム",
        "wait_hint": "返信を待つ間に遊びましょう 🐾",
        "tetris": "🧱 猫テトリス", "lines": "ライン",
        "tetris_hint": "←→↓ — 移動 · ↑ — 回転 · スペース — 落下 · P — 一時停止",
        "mines": "💣 マインスイーパー",
        "mines_hint": "左クリック — 開く · 右クリック — 旗 · R — 新しいゲーム",
        "win": "あなたの勝ち！", "lose": "あなたの負け", "draw": "引き分け",
        "cards": "🃏 戦争", "card_ranks": "6 7 8 9 10 J Q K A",
        "cards_you": "あなた", "cards_cat": "猫",
        "cards_move": "クリックかスペース — 次のラウンド",
        "cards_war": "⚔️ 戦争！カードは場に残ります",
        "mario": "🐱 スーパーキャット", "lives": "残機", "coins": "コイン",
        "mario_hint": "←→ — 走る · ↑ / スペース — ジャンプ · ネズミを踏もう！",
        "kart": "🏎 キャットカート", "lap": "ラップ", "place": "順位",
        "kart_hint": "↑ — アクセル · ←→ — ハンドル · ↓ — ブレーキ",
        "arka": "🧱 キャットノイド",
        "arka_hint": "マウス / ←→ — ラケット · ボールを落とさないで",
        "g15": "🧩 15パズル", "moves": "手数", "solved": "完成！",
        "pairs": "🎴 神経衰弱",
        "xo": "⭕ 三目並べ", "xo_you": "あなたの番", "xo_cat": "猫の番",
        "chess": "♞ チェス", "checkers": "チェッカー", "turn_white": "白の番",
        "tanks": "▮ 戦車", "gsearch": "全体検索", "media_search": "チャットのメディア",
        "translate_chat": "チャットを翻訳", "translating": "翻訳中…",
        "gs_hint": "すべてのチャットとメッセージを検索",
        "gs_chats": "チャット", "gs_msgs": "メッセージ",
        "cat_photos": "📷 写真", "cat_videos": "🎬 動画", "cat_links": "🔗 リンク",
        "cat_music": "🎵 音楽", "cat_contacts": "👤 連絡先",
        "wp_fish": "お魚 🐟", "wp_hearts": "ハート 💕",
        "ctx_copy": "テキストをコピー", "ctx_reply": "返信", "ctx_fwd": "転送",
        "ctx_del": "削除", "ctx_pin": "ピン留め", "fwd_pick": "転送先…",
        "fwd_ok": "転送しました", "pin_ok": "ピン留めしました", "del_ok": "削除しました",
        "replying": "メッセージに返信", "profile": "プロフィール",
        "info_user": "ユーザー名", "info_phone": "電話", "info_about": "自己紹介",
        "day_today": "今日",
        "set_trlang": "翻訳言語", "tr_input": "書いた内容を翻訳",
        "set_device": "デバイス（クライアント）", "dev_desktop": "PC (CatGram)",
        "dev_android": "Android (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "再起動後に適用されます", "set_notify": "トレイ通知",
        "set_nsound": "通知音", "set_stream": "動画をダウンロードせず再生（ストリーム）",
        "wp_file": "PCから📁", "set_wall_pick": "ファイルを選ぶ…",
        "play_app": "遊ぶ（ボットのミニアプリ）",
        "not_bot": "ボットではありません：ミニアプリはボット専用です",
        "set_catcursor": "棒を持った猫カーソル 🐱",
        "turn_black": "黒の番", "in_check": "王手！", "white_wins": "白の勝ち！",
        "black_wins": "黒の勝ち！", "stalemate": "ステイルメイト — 引き分け",
        "must_capture": "取るのが必須！",
        "xo_win": "あなたの勝ち！", "xo_lose": "猫の勝ち",
        "stickers": "スタンプ", "st_load": "スタンプを読み込み中…",
        "st_none": "スタンプセットがありません", "st_fail": "プレビューを読み込めません",
        "st_webp": "この Qt ビルドは WebP を読めません — スタンプが表示されません。"
                   "dwebp（libwebp-tools パッケージ）、ffmpeg または ImageMagick を"
                   "インストールしてください",
        "call": "Telegram で通話", "call_tel": "電話番号にかける (tel:)",
        "call_title": "通話",
        "call_need_lib": "通話には ntgcalls ライブラリが必要です。<br>"
                         "インストール: <code>pip install ntgcalls</code>",
        "call_no_audio": "マイクもスピーカーも見つかりません",
        "call_hint_throw": "オーディオ機器の一覧を取得できませんでした: {err}",
        "call_hint_libs": "システムのサウンドライブラリが見つかりません。インストール"
                          "して catgram を再起動してください:\nDebian/Ubuntu: sudo apt "
                          "install libpulse0 libasound2\nFedora: sudo dnf install "
                          "pulseaudio-libs alsa-lib\nArch: sudo pacman -S libpulse "
                          "alsa-lib\nターミナルで確認: ldconfig -p | grep libpulse",
        "call_hint_server": "サウンドサーバー (PulseAudio/PipeWire) にこのセッションから"
                            "アクセスできません。通常のデスクトップのターミナルから "
                            "catgram を起動してください（SSH や sudo 経由ではなく）、"
                            "サウンドが機能するか確認してください。",
        "call_hint_pactl": "サウンドサーバーは動いているようですが、ntgcalls が機器を"
                           "認識しません。同じターミナルで: pactl list short — を実行"
                           "し、出力を開発者に送ってください。",
        "call_hint_mic": "マイクが見えません（スピーカーは見つかりました）。マイクを"
                         "接続するか、システムのサウンド設定で有効にしてください。",
        "call_hint_spk": "スピーカーが見えません（マイクは見つかりました）。システムの"
                         "サウンド設定で出力機器を確認してください。",
        "call_bad_lib": "インストール済みの ntgcalls {ver} は使えません: {missing} が"
                        "ありません。<br><code>pip install -U ntgcalls</code> を試して"
                        "ください（catgram と同じ環境で）。改善しない場合はこの文章を"
                        "開発者に送ってください:<br>{have}",
        "call_busy": "すでに別の通話中です",
        "call_no_phone": "電話番号が非表示です（プライバシー設定）",
        "call_people_only": "通話は人とのチャットでのみ可能です",
        "call_tel_fail": "tel: リンクを開くアプリがありません。何かをインストールするか"
                         "（例: KDE Connect / GSConnect）、手動でダイヤルしてください。",
        "call_dialing": "呼び出し中…", "call_incoming": "着信…",
        "call_connecting": "接続中…", "call_talking": "通話中",
        "call_accept": "応答", "call_decline": "拒否", "call_end": "終了",
        "call_mute": "マイクをミュート", "call_unmute": "ミュート解除",
        "call_ended": "通話が終わりました", "call_missed": "応答なし",
        "call_peer_busy": "拒否されたか話し中", "call_failed": "接続が切れました",
    },
    "ar": {
        "title": "🐱 catgram", "login": "🐱 catgram — تسجيل الدخول",
        "api_id": "api_id (my.telegram.org → API development tools):",
        "api_hash": "api_hash:",
        "phone": "رقم الهاتف (+رمز الدولة والرقم):",
        "bad_phone": "الرقم غير صالح. استخدم الصيغة الدولية: +<رمز الدولة><الرقم> "
                     "(بدون صفر في البداية)، مثال +12025550123",
        "code": "الرمز من تيليجرام:", "bad_code": "رمز خاطئ، حاول مجددًا:",
        "pw": "كلمة مرور التحقق بخطوتين:",
        "bad_pw": "كلمة مرور خاطئة، مرة أخرى:",
        "write": "مياو… اكتب رسالة واضغط Enter",
        "find_chats": "البحث في المحادثات…",
        "find_msgs": "البحث في هذه المحادثة… (Enter — بحث، Esc — إغلاق)",
        "pick_chat": "اختر محادثة من اليسار", "menu": "catgram",
        "settings": "الإعدادات…", "accounts": "الحسابات…", "search": "البحث في المحادثة",
        "updates": "التحقق من التحديثات", "quit": "خروج", "me": "أنا",
        "m_sticker": "[ملصق]", "m_photo": "[صورة]", "m_voice": "[رسالة صوتية]",
        "m_video": "[فيديو]", "m_file": "[ملف]", "m_other": "[مرفق]",
        "set_title": "الإعدادات", "set_lang": "اللغة", "set_theme": "السمة",
        "theme_dark": "داكن", "theme_light": "فاتح", "set_font": "حجم الخط",
        "set_avatars": "الصور الرمزية", "av_real": "صور حقيقية (قطة إن لم توجد)",
        "av_cats": "قطط فقط", "av_none": "بدون",
        "set_photos": "إظهار الصور في المحادثة",
        "set_noise": "كبت الضوضاء في المكالمات",
        "set_wallpaper": "خلفية الدردشة", "wp_none": "بدون", "wp_paws": "آثار الأقدام 🐾",
        "wp_stars": "نجوم ✨",
        "noise_off": "كبت الضوضاء غير متاح",
        "noise_on": "كبت الضوضاء: {name}", "test_noise": "اختبار",
        "acc_add": "إضافة حساب", "acc_switch": "تبديل", "acc_remove": "حذف",
        "acc_del_q": "حذف الحساب {name}؟",
        "acc_switch_q": "إعادة تشغيل catgram والتبديل إلى {name}؟",
        "acc_limit": "تم بلوغ الحد: 100 حساب إضافي",
        "info": "معلومات المحادثة", "about": "الوصف",
        "username": "اسم المستخدم", "phone_lbl": "الهاتف", "members": "الأعضاء",
        "set_upd_start": "التحقق من التحديثات عند التشغيل",
        "set_upd_url": "عنوان التحديثات (https)",
        "upd_no_url": "لم يُضبط عنوان التحديثات. أضفه في الإعدادات.",
        "upd_latest": "لديك أحدث إصدار.", "upd_new": "يتوفر إصدار جديد",
        "upd_err": "تعذر التحقق من التحديثات",
        "res": "نتائج البحث", "nothing": "لم يُعثر على شيء",
        "online": "خرخر", "offline": "لا يخرخر",
        "attach_video": "إرسال فيديو", "pick_video": "اختر فيديو",
        "video_files": "فيديو", "all_files": "كل الملفات",
        "sending_video": "جارٍ إرسال الفيديو",
        "hist_start": "· بداية المحادثة ·",
        "hist_loading": "جارٍ تحميل السجل…", "error": "خطأ",
        "games": "🎮 الألعاب", "snake": "🐍 الثعبان", "g2048": "🐾 2048",
        "emoji": "الرموز التعبيرية", "score": "النقاط", "best": "الأفضل",
        "game_over": "انتهت اللعبة", "paused": "إيقاف مؤقت",
        "again": "اضغط R للعب مرة أخرى",
        "game_hint": "مسافة — إيقاف · R — لعبة جديدة",
        "wait_hint": "العب ريثما يأتي الرد 🐾",
        "tetris": "🧱 قطريس", "lines": "الصفوف",
        "tetris_hint": "←→↓ — تحريك · ↑ — تدوير · مسافة — إسقاط · P — إيقاف",
        "mines": "💣 كاسحة الألغام",
        "mines_hint": "زر أيسر — فتح · زر أيمن — علم · R — لعبة جديدة",
        "win": "فزت!", "lose": "خسرت", "draw": "تعادل",
        "cards": "🃏 الحرب", "card_ranks": "6 7 8 9 10 J Q K A",
        "cards_you": "أنت", "cards_cat": "القطة",
        "cards_move": "نقرة أو مسافة — الجولة التالية",
        "cards_war": "⚔️ حرب! تبقى البطاقات على الطاولة",
        "mario": "🐱 القطة الخارقة", "lives": "الأرواح", "coins": "العملات",
        "mario_hint": "←→ — جري · ↑ / مسافة — قفز · اقفز على الفئران!",
        "kart": "🏎 كارت القطط", "lap": "لفّة", "place": "المركز",
        "kart_hint": "↑ — بنزين · ←→ — مقود · ↓ — فرامل",
        "arka": "🧱 كاتانويد",
        "arka_hint": "الفأرة / ←→ — المضرب · لا تُسقط الكرة",
        "g15": "🧩 لغز الـ 15", "moves": "الحركات", "solved": "تم الحل!",
        "pairs": "🎴 اعثر على الأزواج",
        "xo": "⭕ إكس-أو", "xo_you": "دورك", "xo_cat": "دور القطة",
        "chess": "♞ شطرنج", "checkers": "الداما", "turn_white": "دور الأبيض",
        "tanks": "▮ دبابات", "gsearch": "بحث عام", "media_search": "وسائط الدردشة",
        "translate_chat": "ترجم الدردشة", "translating": "جارٍ الترجمة…",
        "gs_hint": "ابحث في كل الدردشات والرسائل",
        "gs_chats": "الدردشات", "gs_msgs": "الرسائل",
        "cat_photos": "📷 الصور", "cat_videos": "🎬 الفيديو", "cat_links": "🔗 الروابط",
        "cat_music": "🎵 الموسيقى", "cat_contacts": "👤 جهات الاتصال",
        "wp_fish": "أسماك 🐟", "wp_hearts": "قلوب 💕",
        "ctx_copy": "نسخ النص", "ctx_reply": "رد", "ctx_fwd": "إعادة توجيه",
        "ctx_del": "حذف", "ctx_pin": "تثبيت", "fwd_pick": "إعادة توجيه إلى…",
        "fwd_ok": "أُعيد توجيهه", "pin_ok": "ثُبّت", "del_ok": "حُذف",
        "replying": "الرد على رسالة", "profile": "الملف الشخصي",
        "info_user": "اسم المستخدم", "info_phone": "الهاتف", "info_about": "نبذة",
        "day_today": "اليوم",
        "set_trlang": "لغة الترجمة", "tr_input": "ترجم ما تكتب",
        "set_device": "الجهاز (العميل)", "dev_desktop": "حاسوب (CatGram)",
        "dev_android": "أندرويد (Samsung)", "dev_ios": "iPhone (iOS)",
        "dev_note": "يُطبَّق بعد إعادة التشغيل", "set_notify": "إشعارات الدرج",
        "set_nsound": "صوت الإشعارات", "set_stream": "بث الفيديو (بدون تنزيل كامل)",
        "wp_file": "من الحاسوب 📁", "set_wall_pick": "اختر ملفًا…",
        "play_app": "العب (تطبيق البوت المصغر)",
        "not_bot": "هذا ليس بوتًا: التطبيقات المصغرة لدى البوتات فقط",
        "set_catcursor": "مؤشر قطة بعصا 🐱",
        "turn_black": "دور الأسود", "in_check": "كش!", "white_wins": "فاز الأبيض!",
        "black_wins": "فاز الأسود!", "stalemate": "طريق مسدود — تعادل",
        "must_capture": "الأخذ إجباري!",
        "xo_win": "فزت!", "xo_lose": "فازت القطة",
        "stickers": "الملصقات", "st_load": "جارٍ تحميل الملصقات…",
        "st_none": "لا توجد حزم ملصقات", "st_fail": "تعذر تحميل المعاينات",
        "st_webp": "لا تقرأ نسخة Qt هذه صيغة WebP — لن تظهر الملصقات. ثبّت "
                   "dwebp (حزمة libwebp-tools) أو ffmpeg أو ImageMagick",
        "call": "مكالمة عبر تيليجرام", "call_tel": "الاتصال بالرقم (tel:)",
        "call_title": "مكالمة",
        "call_need_lib": "تحتاج المكالمات مكتبة ntgcalls.<br>"
                         "ثبّتها: <code>pip install ntgcalls</code>",
        "call_no_audio": "لم يُعثر على ميكروفون أو مكبرات صوت",
        "call_hint_throw": "تعذر الحصول على قائمة أجهزة الصوت: {err}",
        "call_hint_libs": "لم تُعثر مكتبات الصوت للنظام. ثبّتها وأعد تشغيل "
                          "catgram:\nDebian/Ubuntu: sudo apt install libpulse0 "
                          "libasound2\nFedora: sudo dnf install pulseaudio-libs "
                          "alsa-lib\nArch: sudo pacman -S libpulse alsa-lib\n"
                          "تحقق في الطرفية: ldconfig -p | grep libpulse",
        "call_hint_server": "خادم الصوت (PulseAudio/PipeWire) غير متاح من هذه الجلسة. "
                            "شغّل catgram من طرفية سطح المكتب العادية (ليس عبر SSH "
                            "وليس عبر sudo) وتأكد من أن الصوت يعمل.",
        "call_hint_pactl": "يبدو أن خادم الصوت يعمل لكن ntgcalls لا يرى الأجهزة. "
                           "نفّذ في الطرفية نفسها: pactl list short — وأرسل الناتج "
                           "إلى المطوّر.",
        "call_hint_mic": "لا يظهر الميكروفون (وُجدت مكبرات الصوت). وصّل ميكروفونًا أو "
                         "فعّله من إعدادات صوت النظام.",
        "call_hint_spk": "لا تظهر مكبرات الصوت (وُجد ميكروفون). تحقق من أجهزة الإخراج "
                        "في إعدادات صوت النظام.",
        "call_bad_lib": "نسخة ntgcalls {ver} المثبتة لا تناسب: ينقص {missing}.<br>"
                        "جرّب <code>pip install -U ntgcalls</code> (في البيئة نفسها "
                        "التي يعمل فيها catgram). إن لم يفد، أرسل هذا النص إلى "
                        "المطوّر:<br>{have}",
        "call_busy": "هناك مكالمة أخرى جارية",
        "call_no_phone": "رقم الهاتف غير ظاهر (إعدادات الخصوصية)",
        "call_people_only": "المكالمات متاحة في محادثات الأشخاص فقط",
        "call_tel_fail": "لا يوجد تطبيق يفتح روابط tel:. ثبّت واحدًا (مثل KDE "
                         "Connect / GSConnect) أو اطلب الرقم يدويًا.",
        "call_dialing": "جارٍ الاتصال…", "call_incoming": "مكالمة واردة…",
        "call_connecting": "جارٍ التوصيل…", "call_talking": "في المكالمة",
        "call_accept": "قبول", "call_decline": "رفض", "call_end": "إنهاء",
        "call_mute": "كتم الميكروفون", "call_unmute": "إلغاء الكتم",
        "call_ended": "انتهت المكالمة", "call_missed": "لا رد",
        "call_peer_busy": "مرفوضة أو مشغولة", "call_failed": "انقطع الاتصال",
    },
}


def detect_lang():
    code = (os.environ.get("LC_ALL") or os.environ.get("LANG") or "").lower()
    for lang in ("uk", "ru", "en", "es", "fr", "de", "it", "pt", "pl", "tr", "zh", "ja", "ar"):
        if code.startswith(lang):
            return lang
    return "en"


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
    "tr_lang": detect_lang(),   # язык перевода (переписки и набранного текста)
    "theme": "dark",
    "font_size": 14,
    "avatar_mode": "real",   # real | cats | none
    "wallpaper": "none",     # обои чата: none | paws | stars | fish | hearts | file
    "wallpaper_file": "",    # путь к картинке своих обоев (режим file)
    "device": "desktop",     # каким клиентом нас видит Telegram: desktop | android | ios
                             # («мобильный» режим нужен мини-приложениям вроде Hamster Kombat)
    "notify": True,          # всплывашки в трее о новых сообщениях
    "notify_sound": True,   # звук при уведомлении
    "stream_video": True,    # видео: плеер стартует по буферу, не дожидаясь конца загрузки
    "cat_cursor": True,      # курсор-кот с палочкой
    "show_photos": True,
    "noise_suppression": True,   # шумоподавление в звонках (module-echo-cancel)
    "check_updates": False,
    "update_url": "",
    "account": APP,          # какой аккаунт открывать (основной или catgram-NN)
    "account_labels": {},    # имя файла сессии -> имя владельца из Telegram
    "best_snake": 0,         # рекорд в змейке
    "best_2048": 0,          # рекорд в 2048
    "best_tetris": 0,        # рекорд в котетрисе
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
    if s.get("wallpaper") not in ("none", "paws", "stars", "fish", "hearts", "file"):
        s["wallpaper"] = "none"
    if s.get("device") not in ("desktop", "android", "ios"):   # «мобильный клиент»
        s["device"] = "desktop"
    s["wallpaper_file"] = str(s.get("wallpaper_file") or "")
    s["notify"] = bool(s.get("notify", True))
    s["notify_sound"] = bool(s.get("notify_sound", True))
    s["stream_video"] = bool(s.get("stream_video", True))
    s["cat_cursor"] = bool(s.get("cat_cursor", True))
    if s.get("tr_lang") not in LANGS:   # язык перевода: по умолчанию — язык интерфейса
        s["tr_lang"] = s.get("lang", "en")
    for k in ("best_snake", "best_2048", "best_tetris"):
        try:
            s[k] = max(0, int(s[k]))
        except (TypeError, ValueError):
            s[k] = 0
    s["show_photos"] = bool(s["show_photos"])
    s["noise_suppression"] = bool(s["noise_suppression"])
    s["check_updates"] = bool(s["check_updates"])
    s["update_url"] = str(s["update_url"])
    s["account"] = str(s["account"] or APP)   # после старых версий ключа может не быть
    if not isinstance(s["account_labels"], dict):
        s["account_labels"] = {}
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


def wallpaper_tile(kind):
    """Бесшовный тайл обоев: узор рисуем и за краями, чтобы тайлы сходились.

    Лапки и звёздочки — в цветах текущей темы, полупрозрачные: текст
    сообщений поверх остаётся читабельным, а окно растянули — узор тянется.
    """
    T = 160
    P = pal()
    pm = QPixmap(T, T)
    pm.fill(QColor(P["bg"]))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    deco = QColor(P["input"])
    deco.setAlpha(90)
    rnd = random.Random("catgram-wallpaper-" + kind)   # узор не прыгает между запусками

    def wrapped(fn):
        for dx in (-T, 0, T):   # рисуем с заворотом за край — стык бесшовный
            for dy in (-T, 0, T):
                p.save()
                p.translate(dx, dy)
                fn()
                p.restore()

    def paw(x, y, s, rot):
        def draw():
            p.translate(x, y)
            p.rotate(rot)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(deco)
            p.drawEllipse(QPointF(0.0, 0.0), 5.0 * s, 4.2 * s)          # подушечка
            for i, ox in enumerate((-7.0, -2.4, 2.4, 7.0)):           # пальцы
                p.drawEllipse(QPointF(ox * s, -8.0 * s + abs(i - 1.5) * 1.2 * s),
                              2.2 * s, 2.9 * s)
        wrapped(draw)

    def star(x, y, s):
        def draw():
            p.translate(x, y)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(deco)
            pts = []
            for i in range(10):   # пятиконечная: чередуем внешний/внутренний радиус
                a = -math.pi / 2 + i * math.pi / 5
                r = s * (1.0 if i % 2 == 0 else 0.45)
                pts.append(QPointF(r * math.cos(a), r * math.sin(a)))
            p.drawPolygon(QPolygonF(pts))
        wrapped(draw)

    def fish(x, y, s, rot):
        def draw():
            p.translate(x, y)
            p.rotate(rot)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(deco)
            p.drawEllipse(QPointF(0.0, 0.0), 8.0 * s, 4.0 * s)            # туловище
            p.drawPolygon(QPolygonF([                                       # хвост
                QPointF(-7.0 * s, 0.0), QPointF(-12.0 * s, -4.0 * s),
                QPointF(-12.0 * s, 4.0 * s)]))
            p.setBrush(QColor(P["bg"]))                                    # глаз
            p.drawEllipse(QPointF(5.0 * s, -1.0 * s), 0.8 * s, 0.8 * s)
        wrapped(draw)

    def heart(x, y, s, rot):
        def draw():
            p.translate(x, y)
            p.rotate(rot)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(deco)
            p.drawEllipse(QPointF(-3.2 * s, -2.6 * s), 3.6 * s, 3.6 * s)  # левая доля
            p.drawEllipse(QPointF(3.2 * s, -2.6 * s), 3.6 * s, 3.6 * s)   # правая доля
            p.drawPolygon(QPolygonF([                                      # остриё
                QPointF(-6.4 * s, -0.8 * s), QPointF(6.4 * s, -0.8 * s),
                QPointF(0.0, 7.5 * s)]))
        wrapped(draw)

    if kind == "paws":
        for _ in range(6):
            paw(rnd.uniform(0, T), rnd.uniform(0, T),
                rnd.uniform(0.55, 0.95), rnd.uniform(-40, 40))
    elif kind == "fish":
        for _ in range(5):
            fish(rnd.uniform(0, T), rnd.uniform(0, T),
                 rnd.uniform(0.5, 0.9), rnd.uniform(-45, 45))
    elif kind == "hearts":
        for _ in range(7):
            heart(rnd.uniform(0, T), rnd.uniform(0, T),
                  rnd.uniform(0.55, 1.0), rnd.uniform(-30, 30))
    else:
        for _ in range(8):
            star(rnd.uniform(0, T), rnd.uniform(0, T), rnd.uniform(3.0, 6.0))
    p.end()
    return pm


def wallpaper_path():
    """Файл обоев в кэше (или оригинал) или None, если обои выключены."""
    if S.get("wallpaper") == "file":   # свои обои: картинка с этого компьютера
        src = str(S.get("wallpaper_file") or "")
        if not src:
            return None
        try:
            pm = QPixmap(src)   # Qt сам понимает png/jpg/bmp/webp (плагины)
            if pm.isNull():
                return None
            if pm.width() > 1920 or pm.height() > 1200:   # QSS не умеет растягивать,
                # огромное фото уменьшаем один раз и держим в кэше
                pm = pm.scaled(1920, 1200, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                out = CACHE_DIR / "catgram-wallpaper-custom.png"
                if not pm.save(str(out), "PNG"):
                    return None
                return str(out)
            return src
        except Exception:
            return None
    if S.get("wallpaper") not in ("paws", "stars", "fish", "hearts"):
        return None
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / "catgram-wallpaper.png"
        if not wallpaper_tile(S["wallpaper"]).save(str(path), "PNG"):
            return None
        return path
    except Exception:
        return None


def make_style():
    css = QSS.substitute(pal(), size=S["font_size"])
    wp = wallpaper_path()
    if wp is not None:   # QSS тайлит background-image сам — выйдет бесшовная стена
        url = str(wp).replace("\\", "/").replace(" ", "%20")
        if S.get("wallpaper") == "file":   # свои обои: один раз, по центру
            css += (f"\nQTextBrowser#chat_view {{ background-image: url({url}); "
                    f"background-repeat: no-repeat; background-position: center; }}")
        else:
            css += f"\nQTextBrowser#chat_view {{ background-image: url({url}); }}"
    return css


# ---------- коты ----------

FUR = ["#f5a97f", "#8aadf4", "#a6da95", "#c6a0f6", "#eed49f",
       "#ed8796", "#8bd5ca", "#f5bde6", "#b7bdf8"]
EYES = ["#2d2f3d", "#40a02b", "#1e66f5", "#df8e1d"]


def cat_cursor_pixmap():
    """Курсор-кот с палочкой 🐱: палочка — указатель (её кончик = точка клика),
    кот сидит у нижнего конца и держит её лапой. Белая палочка с чёрным
    контуром видна и на светлой, и на тёмной теме."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for w, col in ((5.0, QColor("#1c1b22")), (2.4, QColor("#ffffff"))):   # палочка
        p.setPen(QPen(col, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(1.5, 1.5), QPointF(14.0, 14.0))
    fur, dark = QColor("#f5a97f"), QColor("#1c1b22")
    p.setPen(QPen(dark, 1.6))
    p.setBrush(fur)
    p.drawEllipse(QPointF(14.5, 14.5), 3.0, 3.0)   # лапа держит палочку
    p.drawPolygon(QPolygonF([QPointF(14.5, 16.5), QPointF(16.0, 9.5),   # уши
                             QPointF(20.5, 13.5)]))
    p.drawPolygon(QPolygonF([QPointF(28.5, 16.5), QPointF(27.0, 9.5),
                             QPointF(22.5, 13.5)]))
    p.drawEllipse(QPointF(21.5, 21.5), 8.6, 8.6)   # голова
    p.setPen(Qt.PenStyle.NoPen)                    # глаза и носик
    p.setBrush(dark)
    p.drawEllipse(QPointF(18.5, 21.0), 1.4, 1.9)
    p.drawEllipse(QPointF(24.5, 21.0), 1.4, 1.9)
    p.setBrush(QColor("#ed8796"))
    p.drawEllipse(QPointF(21.5, 24.0), 1.3, 1.0)
    p.setPen(QPen(dark, 1.1))                      # усы
    p.drawLine(QPointF(13.0, 23.0), QPointF(9.5, 22.0))
    p.drawLine(QPointF(13.0, 25.0), QPointF(9.5, 25.5))
    p.drawLine(QPointF(30.0, 23.0), QPointF(31.8, 22.3))
    p.drawLine(QPointF(30.0, 25.0), QPointF(31.8, 25.6))
    p.end()
    return pm


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
    msgCtx = pyqtSignal(str)   # правый клик по сообщению: ref «чат/сообщение»

    def __init__(self, images):
        super().__init__()
        self.images = images
        self.pending = {}
        self.setOpenExternalLinks(False)   # http-ссылки и catvid: обрабатывает CatGram
        self.setOpenLinks(False)

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

    def contextMenuEvent(self, e):
        """Правый клик по сообщению — как контекстное меню Telegram Desktop.

        У каждого сообщения метка времени является якорем msg:чат/сообщение;
        идём от места клика назад по блоку до этого якоря.
        """
        cur = self.cursorForPosition(e.pos())
        start = cur.block().position()
        p = cur.position()
        for i in range(4000):
            q = p - i
            if q <= start:
                break
            c = QTextCursor(self.document())
            c.setPosition(q)
            fmt = c.charFormat()
            if fmt.isAnchor():
                a = fmt.anchorHref()
                if a and a.startswith("msg:"):
                    self.msgCtx.emit(a[4:])
                    return
        super().contextMenuEvent(e)


class PhotoViewer(QDialog):
    """Полноэкранный просмотр фото — по мотивам оверлея Media::View из Telegram Desktop.

    Листание стрелками и кнопками ‹ ›, зум колесом мыши и +/−/0, Esc — закрыть.
    """

    def __init__(self, parent, items, index):
        super().__init__(parent)
        self.items = items          # [(id сообщения, QImage или None)] хронологически
        self.index = max(0, min(index, len(items) - 1))
        self.zoom = 1.0
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("🐱 " + tr("m_photo"))
        self.prev_btn = QPushButton("‹", self)
        self.next_btn = QPushButton("›", self)
        self.close_btn = QPushButton("✕", self)
        for b in (self.prev_btn, self.next_btn, self.close_btn):
            b.setFixedSize(44, 44)
            f = b.font()
            f.setPointSize(15)
            b.setFont(f)
        self.counter = QLabel(self)
        self.counter.setStyleSheet("color: #cad3f5; background: rgba(0,0,0,96);"
                                   "border-radius: 8px; padding: 2px 8px;")
        self.prev_btn.clicked.connect(lambda: self.turn(-1))
        self.next_btn.clicked.connect(lambda: self.turn(1))
        self.close_btn.clicked.connect(self.accept)
        self.update_counter()
        self.showMaximized()

    def turn(self, d):
        if len(self.items) < 2:
            return
        self.index = (self.index + d) % len(self.items)
        self.zoom = 1.0
        self.update_counter()
        self.update()

    def update_counter(self):
        mid, _img = self.items[self.index]
        self.counter.setText(f"{self.index + 1} / {len(self.items)}  ·  #{mid}")

    def wheelEvent(self, e):
        self.zoom = max(0.2, min(5.0, self.zoom * (1.1 if e.angleDelta().y() > 0 else 1 / 1.1)))
        self.update()

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Left:
            self.turn(-1)
        elif k == Qt.Key.Key_Right:
            self.turn(1)
        elif k in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.accept()
        elif k == Qt.Key.Key_Plus:
            self.zoom = min(5.0, self.zoom * 1.1)
            self.update()
        elif k == Qt.Key.Key_Minus:
            self.zoom = max(0.2, self.zoom / 1.1)
            self.update()
        elif k == Qt.Key.Key_0:
            self.zoom = 1.0
            self.update()
        else:
            super().keyPressEvent(e)

    def resizeEvent(self, e):
        h = self.height()
        self.prev_btn.move(16, h // 2 - 22)
        self.next_btn.move(self.width() - 60, h // 2 - 22)
        self.close_btn.move(self.width() - 60, 12)
        self.counter.move(16, 12)
        super().resizeEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101018"))
        _mid, img = self.items[self.index]
        if img is not None and not img.isNull():
            pm = QPixmap.fromImage(img) if isinstance(img, QImage) else QPixmap(img)
            fit = min(self.width() / img.width(), self.height() / img.height(), 1.0)
            scaled = pm.scaled(max(1, int(img.width() * fit * self.zoom)),
                              max(1, int(img.height() * fit * self.zoom)),
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap((self.width() - scaled.width()) // 2,
                         max(0, (self.height() - scaled.height()) // 2), scaled)
        p.end()


class VideoViewer(QDialog):
    """Встроенный просмотр видео (как видеопросмотр Telegram Desktop).

    «▶» в сообщении — видео стримится/скачивается в кэш и играет здесь
    (QtMultimedia). Под видео — панель управления: кнопка «Играть/Пауза»,
    шкала прокрутки, время, громкость и кнопка на весь экран (⛶, или F).
    Space — пауза, Esc — выход (из полного экрана — сначала в окно).
    Нет QtMultimedia или аудио-бэкенда (например, pipewire) — открывается
    системный плеер.
    """

    def __init__(self, parent, path, fallback):
        super().__init__(parent)
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("🐱 " + tr("m_video"))
        self.fallback = fallback
        self.errored = False   # чтобы ошибка плеера не звала fallback дважды
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.vw = QVideoWidget(self)
        lay.addWidget(self.vw, 1)

        bar = QWidget(self)   # панель управления под видео
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 4, 8, 4)
        self.play_btn = QPushButton("⏸")   # та самая кнопка «играть»
        self.play_btn.setFixedWidth(44)
        self.play_btn.clicked.connect(self.toggle_play)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self.player_seek)
        self.time_lbl = QLabel("0:00 / 0:00")
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(70)
        self.vol.setMaximumWidth(120)
        self.vol.valueChanged.connect(self.on_vol)
        self.full_btn = QPushButton("⛶")   # на весь экран
        self.full_btn.setFixedWidth(36)
        self.full_btn.clicked.connect(self.toggle_full)
        bl.addWidget(self.play_btn)
        bl.addWidget(self.seek, 1)
        bl.addWidget(self.time_lbl)
        bl.addWidget(QLabel("🔊"))
        bl.addWidget(self.vol)
        bl.addWidget(self.full_btn)
        lay.addWidget(bar)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.7)
        self.player.setVideoOutput(self.vw)
        self.player.setAudioOutput(self.audio)
        self.player.errorOccurred.connect(self.on_error)
        self.player.durationChanged.connect(self.on_dur)
        self.player.positionChanged.connect(self.on_pos)
        self.player.playbackStateChanged.connect(self.on_state)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.play()

        scr = self.screen().availableGeometry() if self.screen() is not None else None
        if scr is not None:   # окно на 80% экрана; ⛶/F — на весь
            self.resize(scr.width() * 4 // 5, scr.height() * 4 // 5)
        self.show()

    def toggle_play(self, *_):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def player_seek(self, ms):
        self.player.setPosition(ms)

    def on_state(self, state):
        self.play_btn.setText(
            "⏸" if state == QMediaPlayer.PlaybackState.PlayingState else "▶")

    def on_dur(self, ms):
        self.seek.setRange(0, max(0, int(ms)))

    def on_pos(self, ms):
        if not self.seek.isSliderDown():
            self.seek.setValue(int(ms))
        self.time_lbl.setText(f"{self._t(ms)} / {self._t(self.player.duration())}")

    def on_vol(self, v):
        self.audio.setVolume(v / 100)

    def toggle_full(self, *_):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    @staticmethod
    def _t(ms):
        s = max(0, int(ms // 1000))
        return f"{s // 60}:{s % 60:02d}"

    def on_error(self, *_a):
        """Кодека нет или аудио-бэкенда нет (nix-shell без pipewire) —
        отдаём файл системному плееру, окно закрываем."""
        if self.errored:
            return
        self.errored = True
        try:
            self.fallback()
        finally:
            self.accept()

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            if self.isFullScreen():   # из полного экрана — сначала в окно
                self.showNormal()
            else:
                self.player.stop()
                self.accept()
        elif k == Qt.Key.Key_Space:
            self.toggle_play()
        elif k == Qt.Key.Key_F:
            self.toggle_full()
        else:
            super().keyPressEvent(e)


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


async def login(client, title=None):
    await client.connect()
    if await client.is_user_authorized():
        return True
    title = title or tr("login")

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


# ---------- аккаунты ----------

ACCOUNTS_MAX = 100          # дополнительных аккаунтов, помимо основного
RESTART = {"want": False}   # перезапустить catgram (переключение аккаунта)


def account_names():
    """Имена сохранённых аккаунтов: основной «catgram» и «catgram-01»…«catgram-100»."""
    names = []
    try:
        for f in DATA_DIR.glob(f"{APP}*.session"):
            names.append(f.name[:-len(".session")])
    except OSError:
        pass
    names.sort(key=lambda n: (n != APP, n))
    return names


def free_account_slot():
    """Первый свободный слот для нового аккаунта или None, если лимит исчерпан."""
    used = set(account_names())
    for i in range(1, ACCOUNTS_MAX + 1):
        name = f"{APP}-{i:02d}"
        if name not in used:
            return name
    return None


def account_label(name):
    """Как показывать аккаунт в списке: имя из Telegram, если уже входили."""
    label = (S.get("account_labels") or {}).get(name)
    return f"{name}  —  {label}" if label else name


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


class TetrisGame(QWidget):
    """Котетрис: собирайте линии из падающих фигур, пока собеседник печатает.

    Управление: ←→↓ / WASD — движение и мягкий спуск, ↑ / W — поворот,
    Пробел — мгновенный сброс, P — пауза, R — новая игра.
    """

    COLS = 10
    ROWS = 18
    CELL = 26
    TOP = 34
    SIDE = 150   # панель справа: счёт и подсказка
    PIECES = {   # форма фигуры (X — занятая клетка) и её цвет
        "I": (["....", "XXXX", "....", "...."], "#8bd5ca"),
        "J": (["X..", "XXX", "..."], "#8aadf4"),
        "L": (["..X", "XXX", "..."], "#f5a97f"),
        "O": (["XX", "XX"], "#eed49f"),
        "S": ([".XX", "XX.", "..."], "#a6da95"),
        "T": ([".X.", "XXX", "..."], "#c6a0f6"),
        "Z": (["XX.", ".XX", "..."], "#ed8796"),
    }

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(self.COLS * self.CELL + self.SIDE,
                          self.TOP + self.ROWS * self.CELL)
        self.best = S.get("best_tetris", 0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.new_game()

    def new_game(self):
        self.grid = [[None] * self.COLS for _ in range(self.ROWS)]
        self.score = self.lines = 0
        self.paused = self.over = False
        self.timer.start(500)
        self.spawn()
        self.update()

    def hideEvent(self, e):
        self.paused = True          # таб скрыли — игра сама встаёт на паузу
        self.update()
        super().hideEvent(e)

    def fits(self, cells, px, py):
        for x, y in cells:
            bx, by = x + px, y + py
            if bx < 0 or bx >= self.COLS or by >= self.ROWS:
                return False
            if by >= 0 and self.grid[by][bx]:
                return False
        return True

    def spawn(self):
        tpl, color = self.PIECES[random.choice(list(self.PIECES))]
        self.cells = [(x, y) for y, row in enumerate(tpl)
                      for x, ch in enumerate(row) if ch == "X"]
        self.color = color
        self.px = (self.COLS - (max(x for x, _ in self.cells) + 1)) // 2
        self.py = -min(y for _, y in self.cells)
        if not self.fits(self.cells, self.px, self.py):   # новая фигура упёрлась в стопку
            self.over = True
            self.timer.stop()
            self.save_best()

    def save_best(self):
        if self.score > self.best:       # рекорд пишем сразу
            self.best = self.score
            S["best_tetris"] = self.best
            save_settings()

    def tick(self):
        if self.paused or self.over:
            return
        if self.fits(self.cells, self.px, self.py + 1):
            self.py += 1
        else:
            self.lock()
        self.update()

    def lock(self):
        for x, y in self.cells:
            by = y + self.py
            if by < 0:               # фигура зафиксировалась над потолком
                self.over = True
                self.timer.stop()
                self.save_best()
                return
            self.grid[by][x + self.px] = self.color
        full = [y for y in range(self.ROWS) if all(self.grid[y])]
        for y in sorted(full):
            del self.grid[y]
            self.grid.insert(0, [None] * self.COLS)
        self.lines += len(full)
        self.score += {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}[len(full)] \
            * (self.lines // 10 + 1)
        self.timer.setInterval(max(80, 500 - (self.lines // 10) * 40))   # чуть быстрее
        self.save_best()
        if not self.over:
            self.spawn()

    def rotate(self):
        cells = self.cells
        n = max(max(x for x, _ in cells), max(y for _, y in cells)) + 1
        turned = [(n - 1 - y, x) for x, y in cells]   # поворот по часовой в квадрате n×n
        for dx in (0, -1, 1, -2, 2):   # простые «пинки» от стенки
            if self.fits(turned, self.px + dx, self.py):
                self.cells, self.px = turned, self.px + dx
                return

    def keyPressEvent(self, e):
        k = e.key()
        if self.over:
            if k == Qt.Key.Key_R:
                self.new_game()
                e.accept()
            return
        if k == Qt.Key.Key_R:
            self.new_game()
        elif k == Qt.Key.Key_P:
            self.paused = not self.paused
        elif self.paused:
            super().keyPressEvent(e)
            return
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_A):
            if self.fits(self.cells, self.px - 1, self.py):
                self.px -= 1
        elif k in (Qt.Key.Key_Right, Qt.Key.Key_D):
            if self.fits(self.cells, self.px + 1, self.py):
                self.px += 1
        elif k in (Qt.Key.Key_Down, Qt.Key.Key_S):
            if self.fits(self.cells, self.px, self.py + 1):
                self.py += 1
                self.score += 1
        elif k in (Qt.Key.Key_Up, Qt.Key.Key_W):
            self.rotate()
        elif k == Qt.Key.Key_Space:
            while self.fits(self.cells, self.px, self.py + 1):
                self.py += 1
                self.score += 1
            self.lock()
        else:
            super().keyPressEvent(e)
            return
        self.update()
        e.accept()

    def paintEvent(self, _e):
        P = pal()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(P["panel"]))
        p.drawRect(self.rect())
        p.setBrush(QColor(P["bg"]))
        p.drawRoundedRect(QRectF(0, self.TOP, self.COLS * self.CELL,
                                 self.ROWS * self.CELL), 8, 8)

        hud = p.font()
        hud.setPointSize(max(8, S["font_size"] - 2))
        p.setFont(hud)
        p.setPen(QColor(P["dim"]))
        p.drawText(QRectF(8, 4, self.width() / 2, self.TOP - 8),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tr("tetris"))
        side_x = self.COLS * self.CELL + 12
        p.drawText(QRectF(side_x, self.TOP + 6, self.width() - side_x - 6,
                          self.ROWS * self.CELL),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                   | Qt.TextFlag.TextWordWrap,
                   f'{tr("score")}: {self.score}\n{tr("lines")}: {self.lines}\n'
                   f'{tr("best")}: {self.best}\n\n{tr("tetris_hint")}')

        def block(x, y, color):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(x * self.CELL + 1, self.TOP + y * self.CELL + 1,
                                     self.CELL - 2, self.CELL - 2), 4, 4)

        for y in range(self.ROWS):
            for x in range(self.COLS):
                if self.grid[y][x]:
                    block(x, y, self.grid[y][x])
        for x, y in self.cells:   # падающая фигура
            if y + self.py >= 0:
                block(x + self.px, y + self.py, self.color)

        if self.paused or self.over:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(QRectF(0, self.TOP, self.COLS * self.CELL,
                                     self.ROWS * self.CELL), 8, 8)
            big = p.font()
            big.setBold(True)
            big.setPointSize(max(10, S["font_size"]))
            p.setFont(big)
            p.setPen(QColor("white"))
            msg = tr("game_over") if self.over else tr("paused")
            if self.over:
                msg += f'\n{tr("score")}: {self.score}\n{tr("again")}'
            p.drawText(QRectF(0, self.TOP, self.COLS * self.CELL, self.ROWS * self.CELL),
                       Qt.AlignmentFlag.AlignCenter, msg)
        p.end()


class MinesGame(QWidget):
    """Сапёр: ЛКМ открывает клетку, ПКМ ставит флажок; первый клик всегда безопасный.

    Управление: мышь, R — начать заново.
    """

    COLS = 16
    ROWS = 12
    MINES = 24
    CELL = 28
    TOP = 34
    BOTTOM = 26
    NUM = {1: "#8aadf4", 2: "#a6da95", 3: "#ed8796", 4: "#c6a0f6",
           5: "#f5a97f", 6: "#8bd5ca", 7: "#ee99a0", 8: "#99d1c4"}

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(self.COLS * self.CELL,
                          self.TOP + self.ROWS * self.CELL + self.BOTTOM)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.new_game()

    def new_game(self):
        self.field = [[0] * self.COLS for _ in range(self.ROWS)]   # -1 — мина, иначе число соседей
        self.open = [[False] * self.COLS for _ in range(self.ROWS)]
        self.flag = [[False] * self.COLS for _ in range(self.ROWS)]
        self.first = True
        self.dead = self.won = False
        self.t = 0
        self.timer.start(1000)
        self.update()

    def tick(self):
        if not self.first and not (self.dead or self.won):
            self.t += 1
            self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_R:
            self.new_game()
            e.accept()
        else:
            super().keyPressEvent(e)

    def cell_at(self, pos):
        x, y = int(pos.x() // self.CELL), int((pos.y() - self.TOP) // self.CELL)
        if 0 <= x < self.COLS and 0 <= y < self.ROWS and pos.y() >= self.TOP:
            return x, y
        return None

    def mousePressEvent(self, e):
        c = self.cell_at(e.position())
        if c is None:
            return
        x, y = c
        if e.button() == Qt.MouseButton.LeftButton:
            if self.first:
                self.place_mines(x, y)
                self.first = False
            self.reveal(x, y)
        elif e.button() == Qt.MouseButton.RightButton and not (self.dead or self.won):
            if not self.open[y][x]:
                self.flag[y][x] = not self.flag[y][x]
        self.update()

    def place_mines(self, safe_x, safe_y):
        """Первый клик не должен взрываться — мины раскладываем вокруг него."""
        banned = {(safe_x + dx, safe_y + dy)
                  for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        spots = [(x, y) for x in range(self.COLS) for y in range(self.ROWS)
                 if (x, y) not in banned]
        for x, y in random.sample(spots, self.MINES):
            self.field[y][x] = -1
        for y in range(self.ROWS):
            for x in range(self.COLS):
                if self.field[y][x] != -1:
                    self.field[y][x] = sum(
                        1 for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                        if 0 <= x + dx < self.COLS and 0 <= y + dy < self.ROWS
                        and self.field[y + dy][x + dx] == -1)

    def reveal(self, x, y):
        if self.open[y][x] or self.flag[y][x] or self.dead or self.won:
            return
        self.open[y][x] = True
        if self.field[y][x] == -1:
            self.dead = True
            self.timer.stop()
            return
        if self.field[y][x] == 0:   # пустая клетка — раскрываем всех соседей разом
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    if (dx or dy) and 0 <= nx < self.COLS and 0 <= ny < self.ROWS:
                        self.reveal(nx, ny)
        closed = sum(1 for row in self.open for v in row if not v)
        if closed == self.MINES:
            self.won = True
            self.timer.stop()

    def paintEvent(self, _e):
        P = pal()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(P["panel"]))
        p.drawRect(self.rect())
        p.setBrush(QColor(P["bg"]))
        p.drawRoundedRect(QRectF(0, self.TOP, self.width(), self.ROWS * self.CELL), 8, 8)

        hud = p.font()
        hud.setPointSize(max(8, S["font_size"] - 2))
        p.setFont(hud)
        p.setPen(QColor(P["dim"]))
        flags = sum(1 for row in self.flag for f in row if f)
        p.drawText(QRectF(8, 4, self.width() / 2, self.TOP - 8),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"💣 {self.MINES - flags}   ⏱ {self.t}")
        p.drawText(QRectF(self.width() / 2, 4, self.width() / 2 - 8, self.TOP - 8),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "R — ⟳")

        emoji = p.font()
        emoji.setPixelSize(max(12, int(self.CELL * 0.62)))
        num = p.font()
        num.setBold(True)
        num.setPixelSize(max(11, int(self.CELL * 0.5)))
        for y in range(self.ROWS):
            for x in range(self.COLS):
                r = QRectF(x * self.CELL + 1, self.TOP + y * self.CELL + 1,
                           self.CELL - 2, self.CELL - 2)
                if not self.open[y][x]:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(P["input"]))
                    p.drawRoundedRect(r, 5, 5)
                    if self.flag[y][x] or (self.field[y][x] == -1 and self.won):
                        p.setFont(emoji)
                        p.setPen(QColor(P["text"]))
                        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "🚩")
                    elif self.field[y][x] == -1 and self.dead:
                        p.setFont(emoji)
                        p.setPen(QColor(P["text"]))
                        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "💣")
                else:
                    v = self.field[y][x]
                    if v == -1:   # подорвались именно на этой клетке
                        p.setPen(Qt.PenStyle.NoPen)
                        p.setBrush(QColor("#e64553"))
                        p.drawRoundedRect(r, 5, 5)
                        p.setFont(emoji)
                        p.setPen(QColor("white"))
                        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "💥")
                    elif v:
                        p.setFont(num)
                        p.setPen(QColor(self.NUM.get(v, P["text"])))
                        p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(v))
        p.setPen(Qt.PenStyle.NoPen)
        if self.dead or self.won:
            p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(QRectF(0, self.TOP, self.width(), self.ROWS * self.CELL), 8, 8)
            big = p.font()
            big.setBold(True)
            big.setPointSize(max(10, S["font_size"]))
            p.setFont(big)
            p.setPen(QColor("white"))
            msg = tr("win") if self.won else tr("lose")
            p.drawText(QRectF(0, self.TOP, self.width(), self.ROWS * self.CELL),
                       Qt.AlignmentFlag.AlignCenter, f"{msg}\n⏱ {self.t}\n{tr('again')}")
        else:
            p.setFont(hud)
            p.setPen(QColor(P["dim"]))
            p.drawText(QRectF(0, self.TOP + self.ROWS * self.CELL,
                              self.width(), self.BOTTOM),
                       Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                       tr("mines_hint"))
        p.end()


class CardsGame(QWidget):
    """«Пьяница» против кота: оба вскрывают верхнюю карту — старшая забирает стол.

    Одинаковые карты — «спор»: карты остаются на столе, и в следующем раунде
    победитель заберёт всё. Клик или Пробел — раунд, R — новая партия.
    """

    W = 560
    H = 340
    TOP = 34
    CW = 78
    CH = 110
    SUITS = ["♠", "♥", "♦", "♣"]
    RED = ("♥", "♦")

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(self.W, self.TOP + self.H)
        self.new_game()

    def new_game(self):
        deck = [(v, s) for v in range(6, 15) for s in range(4)]
        random.shuffle(deck)
        self.you, self.cat = deque(deck[:18]), deque(deck[18:])
        self.ranks = tr("card_ranks").split()   # подписи достоинств для карт 6..Туза
        self.table = []      # карты на кону: «спор» копит их, пока не определится победитель
        self.show = None     # последние вскрытые карты (игрока, кота)
        self.msg = tr("cards_move")
        self.over = None     # None | "win" | "lose" | "draw"
        self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return) and not self.over:
            self.step()
            e.accept()
        elif e.key() == Qt.Key.Key_R:
            self.new_game()
            e.accept()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if not self.over:
            self.step()

    def step(self):
        if self.over:
            return
        if not self.you and not self.cat:   # спор опустошил обе колоды разом
            self.over = "draw"
        elif not self.you or not self.cat:   # карта нужна, а колода пуста — проигрыш
            self.over = "win" if self.you else "lose"
        else:
            a, b = self.you.popleft(), self.cat.popleft()
            self.table += [a, b]
            self.show = (a, b)
            took = len(self.table)
            if a[0] > b[0]:
                self.you.extend(self.table)
                self.table = []
                self.msg = f'{tr("cards_you")} +{took}'
            elif b[0] > a[0]:
                self.cat.extend(self.table)
                self.table = []
                self.msg = f'{tr("cards_cat")} +{took}'
            else:
                self.msg = tr("cards_war")
        self.update()

    def card(self, p, x, y, card=None, hidden=False):
        """Одна карта: рубашка с котом или лицо с достоинством и мастью."""
        P = pal()
        r = QRectF(x, y, self.CW, self.CH)
        p.setPen(QPen(QColor(P["border"]), 1))
        if hidden:
            p.setBrush(QColor(P["input"]))
            p.drawRoundedRect(r, 8, 8)
            f = p.font()
            f.setPixelSize(34)
            p.setFont(f)
            p.setPen(QColor(P["dim"]))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "🐾")
            return
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(r, 8, 8)
        v, s = card
        red = self.SUITS[s] in self.RED
        f = p.font()
        f.setBold(True)
        f.setPixelSize(20)
        p.setFont(f)
        p.setPen(QColor("#e64553" if red else "#24273a"))
        p.drawText(QRectF(x, y + 6, self.CW, 24),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   f"{self.ranks[v - 6]}{self.SUITS[s]}")
        f.setPixelSize(42)
        p.setFont(f)
        p.drawText(QRectF(x, y + self.CH // 2 - 12, self.CW, self.CH // 2),
                   Qt.AlignmentFlag.AlignCenter, self.SUITS[s])

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
                   f'{tr("cards_you")}: {len(self.you)}')
        p.drawText(QRectF(self.width() / 2, 4, self.width() / 2 - 8, self.TOP - 8),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f'{tr("cards_cat")}: {len(self.cat)}')

        mid = self.TOP + (self.height() - self.TOP - self.CH) // 2
        self.card(p, 24, mid, hidden=True)   # колоды лежат рубашкой вверх
        self.card(p, self.width() - 24 - self.CW, mid, hidden=True)
        if self.show:
            self.card(p, self.width() // 2 - self.CW - 12, mid, self.show[0])
            self.card(p, self.width() // 2 + 12, mid, self.show[1])
        p.setFont(hud)
        p.setPen(QColor(P["text"]))
        p.drawText(QRectF(0, mid - 34, self.width(), 30),
                   Qt.AlignmentFlag.AlignCenter, self.msg)
        if self.table:
            p.setPen(QColor(P["dim"]))
            p.drawText(QRectF(0, mid + self.CH + 4, self.width(), 26),
                       Qt.AlignmentFlag.AlignCenter, f"🎲 +{len(self.table)}")

        if self.over:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(QRectF(0, self.TOP, self.width(), self.height() - self.TOP), 8, 8)
            big = p.font()
            big.setBold(True)
            big.setPointSize(max(10, S["font_size"]))
            p.setFont(big)
            p.setPen(QColor("white"))
            msg = {"win": tr("win"), "lose": tr("lose"), "draw": tr("draw")}[self.over]
            p.drawText(QRectF(0, self.TOP, self.width(), self.height() - self.TOP),
                       Qt.AlignmentFlag.AlignCenter, f"{msg}\n{tr('again')}")
        p.end()


class Game15(QWidget):
    """Пятнашки: двигайте плитки стрелками или мышью, соберите 1-15 по порядку.

    Управление: стрелки / WASD (плитка сдвигается в пустую клетку), клик мышью,
    R — начать заново.
    """

    N = 4
    CELL = 76
    GAP = 8
    TOP = 34

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        side = self.N * self.CELL + (self.N + 1) * self.GAP
        self.setFixedSize(side, self.TOP + side)
        self.new_game()

    def new_game(self):
        self.board = list(range(1, self.N * self.N)) + [0]   # 0 — пустая клетка
        for _ in range(300):   # перемешиваем только честными ходами — всегда решаемо
            blank = self.board.index(0)
            x, y = blank % self.N, blank // self.N
            near = []
            if x > 0:
                near.append(blank - 1)
            if x < self.N - 1:
                near.append(blank + 1)
            if y > 0:
                near.append(blank - self.N)
            if y < self.N - 1:
                near.append(blank + self.N)
            other = random.choice(near)
            self.board[blank], self.board[other] = self.board[other], self.board[blank]
        self.moves = 0
        self.update()

    def solved(self):
        return self.board == list(range(1, self.N * self.N)) + [0]

    def try_move(self, i):
        """Сдвигает плитку i в пустую клетку, если та рядом."""
        blank = self.board.index(0)
        if not 0 <= i < self.N * self.N:
            return False
        if abs(i % self.N - blank % self.N) + abs(i // self.N - blank // self.N) != 1:
            return False
        self.board[blank], self.board[i] = self.board[i], self.board[blank]
        self.moves += 1
        self.update()
        return True

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_R:
            self.new_game()
            e.accept()
            return
        d = MOVES.get(e.key())
        if d:   # стрелка = куда двигается плитка, то есть откуда приходит в пустую
            blank = self.board.index(0)
            x, y = blank % self.N - d[0], blank // self.N - d[1]
            if 0 <= x < self.N and 0 <= y < self.N:
                self.try_move(y * self.N + x)
            e.accept()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        pos = e.position()
        if pos.y() < self.TOP:
            return
        x = int(pos.x() // (self.CELL + self.GAP))
        y = int((pos.y() - self.TOP) // (self.CELL + self.GAP))
        if 0 <= x < self.N and 0 <= y < self.N:
            self.try_move(y * self.N + x)

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
                   f'{tr("moves")}: {self.moves}')
        p.drawText(QRectF(self.width() / 2, 4, self.width() / 2 - 8, self.TOP - 8),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "R — ⟳")

        for i, v in enumerate(self.board):
            if not v:
                continue
            x = self.GAP + (i % self.N) * (self.CELL + self.GAP)
            y = self.TOP + self.GAP + (i // self.N) * (self.CELL + self.GAP)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(FUR[(v - 1) % len(FUR)]))
            p.drawRoundedRect(QRectF(x, y, self.CELL, self.CELL), 8, 8)
            f = p.font()
            f.setBold(True)
            f.setPixelSize(int(self.CELL * 0.4))
            p.setFont(f)
            p.setPen(QColor("#1e2030"))
            p.drawText(QRectF(x, y, self.CELL, self.CELL),
                       Qt.AlignmentFlag.AlignCenter, str(v))
            p.setPen(Qt.PenStyle.NoPen)
            p.setFont(hud)

        if self.solved():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(QRectF(0, self.TOP, self.width(), self.height() - self.TOP), 8, 8)
            big = p.font()
            big.setBold(True)
            big.setPointSize(max(10, S["font_size"]))
            p.setFont(big)
            p.setPen(QColor("white"))
            p.drawText(QRectF(0, self.TOP, self.width(), self.height() - self.TOP),
                       Qt.AlignmentFlag.AlignCenter,
                       f'{tr("solved")}\n{tr("moves")}: {self.moves}\n{tr("again")}')
        p.end()


class PairsGame(QWidget):
    """Найди пару: открывайте по две клетки и запоминайте, где кто живёт.

    Управление: мышь, R — начать заново.
    """

    COLS = 5
    ROWS = 4
    CELL = 86
    GAP = 8
    TOP = 34
    FACES = ["🐱", "🐭", "🐹", "🐰", "🦊", "🐻", "🐼", "🐨", "🐯", "🦁"]

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        w = self.COLS * self.CELL + (self.COLS + 1) * self.GAP
        h = self.ROWS * self.CELL + (self.ROWS + 1) * self.GAP
        self.setFixedSize(w, self.TOP + h)
        self.new_game()

    def new_game(self):
        faces = self.FACES * 2
        random.shuffle(faces)
        self.cards = faces
        self.done = [False] * len(faces)   # угаданные клетки
        self.flip = []                      # временно открытые (их максимум две)
        self.moves = 0
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_R:
            self.new_game()
            e.accept()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        pos = e.position()
        if pos.y() < self.TOP:
            return
        x = int(pos.x() // (self.CELL + self.GAP))
        y = int((pos.y() - self.TOP) // (self.CELL + self.GAP))
        if not (0 <= x < self.COLS and 0 <= y < self.ROWS):
            return
        i = y * self.COLS + x
        if self.done[i] or i in self.flip or len(self.flip) >= 2:
            return
        self.flip.append(i)
        if len(self.flip) == 2:
            self.moves += 1
            a, b = self.flip
            if self.cards[a] == self.cards[b]:   # пара! клетки остаются открытыми
                self.done[a] = self.done[b] = True
                self.flip = []
            else:
                QTimer.singleShot(650, self.hide_flip)   # дать запомнить позиции
        self.update()

    def hide_flip(self):
        if len(self.flip) == 2:   # могли успеть нажать «заново»
            self.flip = []
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
                   f'{tr("moves")}: {self.moves}')
        p.drawText(QRectF(self.width() / 2, 4, self.width() / 2 - 8, self.TOP - 8),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "R — ⟳")

        emoji = p.font()
        emoji.setPixelSize(int(self.CELL * 0.5))
        for i, face in enumerate(self.cards):
            x = self.GAP + (i % self.COLS) * (self.CELL + self.GAP)
            y = self.TOP + self.GAP + (i // self.COLS) * (self.CELL + self.GAP)
            r = QRectF(x, y, self.CELL, self.CELL)
            p.setPen(Qt.PenStyle.NoPen)
            if self.done[i] or i in self.flip:
                p.setBrush(QColor(P["input"]))
                p.drawRoundedRect(r, 8, 8)
                p.setFont(emoji)
                p.setPen(QColor(P["dim"] if self.done[i] else P["text"]))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, face)
            else:
                p.setBrush(QColor(P["panel"]))
                p.drawRoundedRect(r, 8, 8)
                p.setFont(emoji)
                p.setPen(QColor(P["dim"]))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, "🐾")
            p.setFont(hud)

        if all(self.done):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(QRectF(0, self.TOP, self.width(), self.height() - self.TOP), 8, 8)
            big = p.font()
            big.setBold(True)
            big.setPointSize(max(10, S["font_size"]))
            p.setFont(big)
            p.setPen(QColor("white"))
            p.drawText(QRectF(0, self.TOP, self.width(), self.height() - self.TOP),
                       Qt.AlignmentFlag.AlignCenter,
                       f'{tr("win")}\n{tr("moves")}: {self.moves}\n{tr("again")}')
        p.end()


class XoGame(QWidget):
    """Крестики-нолики против кота: кот играет безупречно (минимакс) — попробуйте ничью.

    Управление: клик по клетке, R — новая партия. Кто начинает — чередуется.
    """

    N = 3
    CELL = 118
    GAP = 10
    TOP = 34
    LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6),
             (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        side = self.N * self.CELL + (self.N + 1) * self.GAP
        self.setFixedSize(side, self.TOP + side)
        self.swin = self.scat = self.sdraw = 0   # счёт партий за этот запуск
        self.cat_starts = True   # первый ход всегда за человеком, дальше чередуем
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.cat_move)
        self.new_game()

    def new_game(self):
        self.timer.stop()
        self.board = [None] * (self.N * self.N)   # None | "you" | "cat"
        self.cat_starts = not self.cat_starts
        self.over = None   # None | "you" | "cat" | "draw"
        if self.cat_starts:
            self.timer.start(450)   # кот «подумает» и откроет партию
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_R:
            self.new_game()
            e.accept()
        else:
            super().keyPressEvent(e)

    def winner_line(self):
        for line in self.LINES:
            vals = [self.board[i] for i in line]
            if vals[0] and vals[0] == vals[1] == vals[2]:
                return vals[0], line
        return None

    def cat_turn(self):
        return self.timer.isActive() and not self.over

    def mousePressEvent(self, e):
        if self.over or self.cat_turn():
            return
        pos = e.position()
        if pos.y() < self.TOP:
            return
        x = int(pos.x() // (self.CELL + self.GAP))
        y = int((pos.y() - self.TOP) // (self.CELL + self.GAP))
        if not (0 <= x < self.N and 0 <= y < self.N):
            return
        i = y * self.N + x
        if self.board[i] is not None:
            return
        self.board[i] = "you"
        self.check_after_move()

    def check_after_move(self):
        w = self.winner_line()
        if w:
            self.over = w[0]
            if w[0] == "you":
                self.swin += 1
        elif None not in self.board:
            self.over = "draw"
            self.sdraw += 1
        else:
            self.timer.start(450)   # ход кота: чуть «подумает»
        self.update()

    def cat_move(self):
        if self.over:
            return
        self.board[self.best_move()] = "cat"
        w = self.winner_line()
        if w:
            self.over = w[0]
            self.scat += 1
        elif None not in self.board:
            self.over = "draw"
            self.sdraw += 1
        self.update()

    def best_move(self):
        best, best_i = -2, None
        for i, v in enumerate(self.board):
            if v is None:
                self.board[i] = "cat"
                s = self.minimax(False)
                self.board[i] = None
                if s > best:
                    best, best_i = s, i
        return best_i

    def minimax(self, cat_turn):
        """Кот выигрывает (+1), человек — (−1), ничья — 0; оба играют идеально."""
        w = self.winner_line()
        if w:
            return 1 if w[0] == "cat" else -1
        if None not in self.board:
            return 0
        scores = []
        for i, v in enumerate(self.board):
            if v is None:
                self.board[i] = "cat" if cat_turn else "you"
                scores.append(self.minimax(not cat_turn))
                self.board[i] = None
        return (max if cat_turn else min)(scores)

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
                   f"🐾 {self.swin} : {self.scat} 😺   🤝 {self.sdraw}")
        if self.over:
            msg = {"you": tr("xo_win"), "cat": tr("xo_lose"), "draw": tr("draw")}[self.over]
        elif self.cat_turn():
            msg = tr("xo_cat")
        else:
            msg = tr("xo_you")
        p.drawText(QRectF(self.width() / 2, 4, self.width() / 2 - 8, self.TOP - 8),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, msg)

        step = self.CELL + self.GAP
        emoji = p.font()
        emoji.setPixelSize(int(self.CELL * 0.5))
        for i, v in enumerate(self.board):
            x = self.GAP + (i % self.N) * step
            y = self.TOP + self.GAP + (i // self.N) * step
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(P["input"]))
            p.drawRoundedRect(QRectF(x, y, self.CELL, self.CELL), 10, 10)
            if v:
                p.setFont(emoji)
                p.setPen(QColor(P["text"]))
                p.drawText(QRectF(x, y, self.CELL, self.CELL),
                           Qt.AlignmentFlag.AlignCenter, "🐾" if v == "you" else "😺")
                p.setFont(hud)

        line = self.winner_line()
        if line:   # зачёркиваем победную линию
            _, cells = line
            a, b = cells[0], cells[-1]

            def center(i):
                return QPointF(self.GAP + (i % self.N) * step + self.CELL / 2,
                               self.TOP + self.GAP + (i // self.N) * step + self.CELL / 2)

            p.setPen(QPen(QColor(P["accent"]), 5))
            p.drawLine(center(a), center(b))
        p.end()


class ChessGame(QWidget):
    """Шахматы на двоих за одним экраном: белые и чёрные ходят по очереди.

    Правила честные: рокировка, взятие на проходе, превращение пешки
    (автоматически в ферзя), шах/мат/пат. Ходов «под шах» движок не даст.
    Управление: клик по фигуре — выбрать, клик по клетке — пойти, R — новая.
    """

    N = 8
    CELL = 64
    TOP = 34
    GLYPH = {"P": "♟", "N": "♞", "B": "♝", "R": "♜", "Q": "♛", "K": "♚"}
    LIGHT = QColor("#e8d0aa")
    DARK = QColor("#a97c50")

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        side = self.N * self.CELL
        self.setFixedSize(side, self.TOP + side)
        self.new_game()

    def new_game(self):
        back = "RNBQKBNR"
        self.board = []
        for r in range(8):
            if r == 0: row = ["b" + ch for ch in back]
            elif r == 1: row = ["bP"] * 8
            elif r == 6: row = ["wP"] * 8
            elif r == 7: row = ["w" + ch for ch in back]
            else: row = [None] * 8
            self.board.append(row)
        self.white = True
        self.ep = None          # поле взятия на проходе: (r, c) за только что ходившей пешкой
        self.rights = {"K": True, "Q": True, "k": True, "q": True}   # рокировки
        self.sel = None
        self.targets = []        # [(rr, cc, kind), ...] куда можно идти выбранной фигурой
        self.last = None        # ((r, c), (r, c)) прошлого хода — подсветка
        self.over = None        # None | "mate" | "stalemate"
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_R:
            self.new_game()
            e.accept()
        else:
            super().keyPressEvent(e)

    def cell(self, pos):
        y = pos.y()
        if y < self.TOP:
            return None
        c = int(pos.x() // self.CELL)
        r = int((y - self.TOP) // self.CELL)
        return (r, c) if 0 <= r < 8 and 0 <= c < 8 else None

    def in_board(self, r, c):
        return 0 <= r < 8 and 0 <= c < 8

    def find_king(self, white):
        want = "wK" if white else "bK"
        for r in range(8):
            for c in range(8):
                if self.board[r][c] == want:
                    return r, c
        return 0, 0

    def attacked(self, r, c, by_white):
        """Бьёт ли сторона by_white поле (r, c): пешки, конь, король, линии."""
        pawn, kn, kg = ("wP", "wN", "wK") if by_white else ("bP", "bN", "bK")
        pr = r + 1 if by_white else r - 1   # белая пешка бьёт в сторону меньших r
        for dc in (-1, 1):
            if self.in_board(pr, c + dc) and self.board[pr][c + dc] == pawn:
                return True
        for dr, dc in ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
                       (1, -2), (1, 2), (2, -1), (2, 1)):
            if self.in_board(r + dr, c + dc) and self.board[r + dr][c + dc] == kn:
                return True
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                if self.in_board(r + dr, c + dc) and self.board[r + dr][c + dc] == kg:
                    return True
        for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            rr, cc = r + dr, c + dc
            while self.in_board(rr, cc):
                q = self.board[rr][cc]
                if q:
                    if q[0] == ("w" if by_white else "b"):
                        diag = dr != 0 and dc != 0
                        if (q[1] == "Q" or (q[1] == "R" and not diag)
                                or (q[1] == "B" and diag)):
                            return True
                    break
                rr += dr
                cc += dc
        return False

    def pseudo(self, r, c):
        """Псевдоходы фигуры (без учёта шаха себе): [(rr, cc, kind), ...]."""
        pc = self.board[r][c]
        mine = pc[0]
        out = []
        if pc[1] == "P":
            d = -1 if mine == "w" else 1
            if self.in_board(r + d, c) and not self.board[r + d][c]:
                out.append((r + d, c, "push"))
                start = 6 if mine == "w" else 1
                if r == start and not self.board[r + 2 * d][c]:
                    out.append((r + 2 * d, c, "double"))
            for dc in (-1, 1):
                rr, cc = r + d, c + dc
                if not self.in_board(rr, cc):
                    continue
                q = self.board[rr][cc]
                if q and q[0] != mine:
                    out.append((rr, cc, "take"))
                elif not q and self.ep == (rr, cc):
                    out.append((rr, cc, "ep"))
        elif pc[1] == "N":
            for dr, dc in ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
                           (1, -2), (1, 2), (2, -1), (2, 1)):
                rr, cc = r + dr, c + dc
                if self.in_board(rr, cc):
                    q = self.board[rr][cc]
                    if not q or q[0] != mine:
                        out.append((rr, cc, "take"))
        elif pc[1] == "K":
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    rr, cc = r + dr, c + dc
                    if self.in_board(rr, cc):
                        q = self.board[rr][cc]
                        if not q or q[0] != mine:
                            out.append((rr, cc, "take"))
        else:
            dirs = []
            if pc[1] in "RQ": dirs += [(0, 1), (0, -1), (1, 0), (-1, 0)]
            if pc[1] in "BQ": dirs += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
            for dr, dc in dirs:
                rr, cc = r + dr, c + dc
                while self.in_board(rr, cc):
                    q = self.board[rr][cc]
                    if not q:
                        out.append((rr, cc, "take"))
                    else:
                        if q[0] != mine:
                            out.append((rr, cc, "take"))
                        break
                    rr += dr
                    cc += dc
        return out

    def raw_move(self, r, c, rr, cc, kind):
        """Меняет доску: сам ход, эп-взятие, превращение, рокировка ладьи."""
        pc = self.board[r][c]
        self.board[rr][cc] = pc
        self.board[r][c] = None
        if kind == "ep":   # сбитая пешка стоит на одной горизонтали с бьющей
            self.board[r][cc] = None
        if pc[1] == "P" and rr == (0 if pc[0] == "w" else 7):
            self.board[rr][cc] = pc[0] + "Q"   # превращение — в ферзя
        if kind == "castle":
            if cc == 6:   # короткая: ладья h -> f
                self.board[rr][5] = self.board[rr][7]
                self.board[rr][7] = None
            else:         # длинная: ладья a -> d
                self.board[rr][3] = self.board[rr][0]
                self.board[rr][0] = None

    def try_move(self, r, c, rr, cc, kind):
        """Не подставляет ли ход собственного короля?"""
        snap = [row[:] for row in self.board]
        self.raw_move(r, c, rr, cc, kind)
        kr, kc = self.find_king(self.white)
        ok = not self.attacked(kr, kc, not self.white)
        self.board = snap
        return ok

    def castles(self):
        """Рокировки текущей стороны: поля пусты и не бьются, ладья на месте."""
        white = self.white
        r = 7 if white else 0
        side = "w" if white else "b"
        out = []
        if self.board[r][4] == side + "K":
            if (self.rights["K" if white else "k"]
                    and not self.board[r][5] and not self.board[r][6]
                    and self.board[r][7] == side + "R"
                    and not self.attacked(r, 4, not white)
                    and not self.attacked(r, 5, not white)
                    and not self.attacked(r, 6, not white)):
                out.append((r, 6, "castle"))
            if (self.rights["Q" if white else "q"]
                    and not self.board[r][1] and not self.board[r][2]
                    and not self.board[r][3]
                    and self.board[r][0] == side + "R"
                    and not self.attacked(r, 4, not white)
                    and not self.attacked(r, 3, not white)
                    and not self.attacked(r, 2, not white)):
                out.append((r, 2, "castle"))
        return out

    def moves_from(self, r, c):
        """Ходы фигуры без шаха себе (плюс рокировки, если это король)."""
        pc = self.board[r][c]
        if pc is None or pc[0] != ("w" if self.white else "b"):
            return []
        out = [(rr, cc, kind) for rr, cc, kind in self.pseudo(r, c)
               if self.try_move(r, c, rr, cc, kind)]
        if pc[1] == "K":
            out += self.castles()
        return out

    def in_check(self):
        kr, kc = self.find_king(self.white)
        return self.attacked(kr, kc, not self.white)

    def side_moves(self):
        """Есть ли у текущей стороны хоть один ход (нет — мат или пат)."""
        for r in range(8):
            for c in range(8):
                if self.moves_from(r, c):
                    return True
        return False

    def make_move(self, r, c, rr, cc, kind):
        pc = self.board[r][c]
        self.raw_move(r, c, rr, cc, kind)
        self.ep = ((r + rr) // 2, c) if kind == "double" else None
        if pc[1] == "K":
            self.rights["K" if pc[0] == "w" else "k"] = False
            self.rights["Q" if pc[0] == "w" else "q"] = False
        for cell, key in (((7, 0), "Q"), ((7, 7), "K"),
                          ((0, 0), "q"), ((0, 7), "k")):
            if (r, c) == cell or (rr, cc) == cell:   # ладья ушла/съедена
                self.rights[key] = False
        self.last = ((r, c), (rr, cc))
        self.white = not self.white
        self.sel = None
        self.targets = []
        if not self.side_moves():
            self.over = "mate" if self.in_check() else "stalemate"
        self.update()

    def mousePressEvent(self, e):
        rc = self.cell(e.position())
        if rc is None or self.over:
            return
        r, c = rc
        if self.sel is not None:
            for rr, cc, kind in self.targets:
                if (rr, cc) == (r, c):
                    sr, sc = self.sel
                    self.make_move(sr, sc, rr, cc, kind)
                    return
        pc = self.board[r][c]
        if pc and pc[0] == ("w" if self.white else "b"):
            self.sel = (r, c)
            self.targets = self.moves_from(r, c)
        else:
            self.sel = None
            self.targets = []
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
        if self.over == "mate":   # ход у проигравшего — победили «не мы»
            msg = tr("white_wins" if not self.white else "black_wins")
        elif self.over == "stalemate":
            msg = tr("stalemate")
        else:
            msg = tr("turn_white" if self.white else "turn_black")
            if self.in_check():
                msg += "  " + tr("in_check")
        p.setPen(QColor(P["dim"]))
        p.drawText(QRectF(8, 4, self.width() - 16, self.TOP - 8),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, msg)

        glyph_font = p.font()
        glyph_font.setPixelSize(int(self.CELL * 0.72))
        for r in range(8):
            for c in range(8):
                x, y = c * self.CELL, self.TOP + r * self.CELL
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(self.LIGHT if (r + c) % 2 == 0 else self.DARK)
                p.drawRect(QRectF(x, y, self.CELL, self.CELL))
                if self.last and (r, c) in self.last:   # подсветка прошлого хода
                    p.setBrush(QColor(P["accent"]))
                    p.setOpacity(0.30)
                    p.drawRect(QRectF(x, y, self.CELL, self.CELL))
                    p.setOpacity(1.0)
                pc = self.board[r][c]
                if pc:
                    p.setFont(glyph_font)
                    rect = QRectF(x, y, self.CELL, self.CELL)
                    glyph = self.GLYPH[pc[1]]
                    p.setPen(QColor("#3b2f1e"))   # тень — обе армии видны на любом поле
                    p.drawText(rect.translated(1.5, 1.5), Qt.AlignmentFlag.AlignCenter, glyph)
                    p.setPen(QColor("#f5f0e6") if pc[0] == "w" else QColor("#241c10"))
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, glyph)
                    p.setFont(hud)

        if self.sel is not None:   # рамка выбора и точки возможных ходов
            r, c = self.sel
            x, y = c * self.CELL, self.TOP + r * self.CELL
            p.setPen(QPen(QColor(P["accent"]), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(x + 2, y + 2, self.CELL - 4, self.CELL - 4), 8, 8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(P["accent"]))
            p.setOpacity(0.75)
            for rr, cc, _kind in self.targets:
                tx, ty = cc * self.CELL, self.TOP + rr * self.CELL
                p.drawEllipse(QPointF(tx + self.CELL / 2, ty + self.CELL / 2), 7, 7)
            p.setOpacity(1.0)
        p.end()


class CheckersGame(QWidget):
    """Шашки на двоих за одним экраном (русские правила).

    Бить обязательно; простая бьёт и назад, дамка летает по всей диагонали.
    После взятия можно бить дальше — цепочка продолжается той же шашкой.
    Дошедшая до последней горизонтали шашка сразу становится дамкой.
    Управление: клик по шашке — выбрать, клик по клетке — пойти, R — новая.
    """

    N = 8
    CELL = 64
    TOP = 34
    LIGHT = QColor("#e8d0aa")
    DARK = QColor("#a97c50")

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        side = self.N * self.CELL
        self.setFixedSize(side, self.TOP + side)
        self.new_game()

    def new_game(self):
        self.board = [[None] * 8 for _ in range(8)]
        for r in range(8):
            for c in range(8):
                if (r + c) % 2 == 1:
                    if r < 3:
                        self.board[r][c] = "b"   # чёрные сверху
                    elif r > 4:
                        self.board[r][c] = "w"   # белые снизу
        self.white = True
        self.sel = None
        self.chain = None      # (r, c) шашки, которая обязана добивать
        self.over = None       # None | "w" | "b" — победитель
        self.last = None
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_R:
            self.new_game()
            e.accept()
        else:
            super().keyPressEvent(e)

    def cell(self, pos):
        y = pos.y()
        if y < self.TOP:
            return None
        c = int(pos.x() // self.CELL)
        r = int((y - self.TOP) // self.CELL)
        return (r, c) if 0 <= r < 8 and 0 <= c < 8 else None

    def side_of(self, pc):
        return None if pc is None else pc.lower()

    def moves_of(self, r, c):
        """(взятия, тихие ходы) шашки. Взятие: (rr, cc, br, bc) — куда и что бито."""
        pc = self.board[r][c]
        caps, steps = [], []
        king = pc in ("W", "B")
        for dr, dc in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            rr, cc = r + dr, c + dc
            if not (0 <= rr < 8 and 0 <= cc < 8):
                continue
            q = self.board[rr][cc]
            if not q:
                if not king and dr != (-1 if pc.lower() == "w" else 1):
                    continue   # простая ходит только вперёд
                steps.append((rr, cc))
                if king:   # дамка летит до упора
                    rr += dr
                    cc += dc
                    while 0 <= rr < 8 and 0 <= cc < 8 and not self.board[rr][cc]:
                        steps.append((rr, cc))
                        rr += dr
                        cc += dc
            elif self.side_of(q) != self.side_of(pc):   # рядом враг — можно бить
                if king:   # дамка перепрыгивает и садится где угодно за врагом
                    r2, c2 = rr + dr, cc + dc
                    while 0 <= r2 < 8 and 0 <= c2 < 8 and not self.board[r2][c2]:
                        caps.append((r2, c2, rr, cc))
                        r2 += dr
                        c2 += dc
                else:   # простая бьёт в любую сторону (в том числе назад)
                    r2, c2 = r + 2 * dr, c + 2 * dc
                    if 0 <= r2 < 8 and 0 <= c2 < 8 and not self.board[r2][c2]:
                        caps.append((r2, c2, rr, cc))
        return caps, steps

    def must_capture(self):
        """Есть ли у текущей стороны хоть одно взятие? (бить обязательно)"""
        for r in range(8):
            for c in range(8):
                pc = self.board[r][c]
                if pc and self.side_of(pc) == ("w" if self.white else "b"):
                    if self.moves_of(r, c)[0]:
                        return True
        return False

    def promote(self, r, c):
        pc = self.board[r][c]
        if pc == "w" and r == 0:
            self.board[r][c] = "W"
        elif pc == "b" and r == 7:
            self.board[r][c] = "B"

    def end_move(self, r, c, rr, cc):
        self.last = ((r, c), (rr, cc))
        self.sel = None
        self.white = not self.white
        alive = any(q and self.side_of(q) == ("w" if self.white else "b")
                    for row in self.board for q in row)
        if not alive:
            self.over = "w" if not self.white else "b"   # побили всех
        else:
            stuck = True
            for r2 in range(8):
                for c2 in range(8):
                    q = self.board[r2][c2]
                    if (q and self.side_of(q) == ("w" if self.white else "b")
                            and any(self.moves_of(r2, c2))):
                        stuck = False
                        break
                if not stuck:
                    break
            if stuck:   # шашки есть, а хода нет — поражение
                self.over = "w" if not self.white else "b"
        self.update()

    def do_step(self, r, c, rr, cc):
        self.board[rr][cc] = self.board[r][c]
        self.board[r][c] = None
        self.promote(rr, cc)
        self.end_move(r, c, rr, cc)

    def do_take(self, r, c, rr, cc, br, bc):
        self.board[rr][cc] = self.board[r][c]
        self.board[r][c] = None
        self.board[br][bc] = None
        self.promote(rr, cc)
        if self.moves_of(rr, cc)[0]:   # можно бить дальше — обязаны продолжать
            self.chain = (rr, cc)
            self.sel = (rr, cc)
            self.last = ((r, c), (rr, cc))
            self.update()
            return
        self.chain = None
        self.end_move(r, c, rr, cc)

    def mousePressEvent(self, e):
        rc = self.cell(e.position())
        if rc is None or self.over:
            return
        r, c = rc
        if self.chain is not None:   # цепочка: добивает только та же шашка
            for rr, cc, br, bc in self.moves_of(*self.chain)[0]:
                if (rr, cc) == (r, c):
                    self.do_take(self.chain[0], self.chain[1], rr, cc, br, bc)
                    return
            self.update()
            return
        take = self.must_capture()
        if self.sel is not None:
            caps, steps = self.moves_of(*self.sel)
            for rr, cc, br, bc in caps:
                if (rr, cc) == (r, c):
                    self.do_take(self.sel[0], self.sel[1], rr, cc, br, bc)
                    return
            if not take:
                for rr, cc in steps:
                    if (rr, cc) == (r, c):
                        self.do_step(self.sel[0], self.sel[1], rr, cc)
                        return
        pc = self.board[r][c]
        if pc and self.side_of(pc) == ("w" if self.white else "b"):
            self.sel = (r, c)
        else:
            self.sel = None
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
        if self.over:
            msg = tr("white_wins" if self.over == "w" else "black_wins")
        else:
            msg = tr("turn_white" if self.white else "turn_black")
            if self.chain is not None or self.must_capture():
                msg += "  " + tr("must_capture")
        p.setPen(QColor(P["dim"]))
        p.drawText(QRectF(8, 4, self.width() - 16, self.TOP - 8),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, msg)

        for r in range(8):
            for c in range(8):
                x, y = c * self.CELL, self.TOP + r * self.CELL
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(self.LIGHT if (r + c) % 2 == 0 else self.DARK)
                p.drawRect(QRectF(x, y, self.CELL, self.CELL))
                if self.last and (r, c) in self.last:
                    p.setBrush(QColor(P["accent"]))
                    p.setOpacity(0.30)
                    p.drawRect(QRectF(x, y, self.CELL, self.CELL))
                    p.setOpacity(1.0)
                pc = self.board[r][c]
                if pc:
                    cx, cy = x + self.CELL / 2, y + self.CELL / 2
                    rad = self.CELL * 0.36
                    p.setPen(QPen(QColor("#3b2f1e"), 2))
                    p.setBrush(QColor("#f2ead9") if self.side_of(pc) == "w"
                               else QColor("#2a2118"))
                    p.drawEllipse(QPointF(cx, cy), rad, rad)
                    if pc in ("W", "B"):   # дамка: отметина в центре
                        p.setPen(Qt.PenStyle.NoPen)
                        p.setBrush(QColor(P["accent"]))
                        p.drawEllipse(QPointF(cx, cy), rad * 0.45, rad * 0.45)

        if self.sel is not None:   # что можно этой шашкой: взятия — кольца, ходы — точки
            r, c = self.sel
            x, y = c * self.CELL, self.TOP + r * self.CELL
            p.setPen(QPen(QColor(P["accent"]), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(x + 2, y + 2, self.CELL - 4, self.CELL - 4), 8, 8)
            caps, steps = self.moves_of(*self.sel)
            take = self.chain is not None or self.must_capture()
            for rr, cc, br, bc in caps:
                tx, ty = cc * self.CELL, self.TOP + rr * self.CELL
                p.setPen(QPen(QColor(P["accent"]), 3))
                p.drawEllipse(QPointF(tx + self.CELL / 2, ty + self.CELL / 2), 11, 11)
            if not take:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(P["accent"]))
                p.setOpacity(0.75)
                for rr, cc in steps:
                    tx, ty = cc * self.CELL, self.TOP + rr * self.CELL
                    p.drawEllipse(QPointF(tx + self.CELL / 2, ty + self.CELL / 2), 7, 7)
                p.setOpacity(1.0)
        p.end()


class MarioGame(QWidget):
    """🐱 Суперкот — платформер: монеты, мыши и финишный флаг.

    Управление: ←→ / A D — бег, ↑ / W / Пробел — прыжок,
    на мышей прыгать сверху, сбоку они кусают. R — заново.
    """

    TOP = 34
    TS = 30          # клетка поля
    VIEW = 20        # клеток видно по горизонтали
    PW, PH = 22, 26  # кот
    EW, EH = 26, 22  # мышь
    RUN = 4.0
    JUMP = -10.5
    GRAV = 0.55
    LEVEL = [   # '.' пусто · '#' земля · 'o' монета · 'e' мышь · 'F' финиш
        "..............................................................................",
        "..........................o.o.o...............................................",
        ".........................#######..............................................",
        "..............................................................................",
        "..............o.o.o..............o.o.....................o.o.o................",
        ".............#######...........######...................#######...............",
        "..............................................................................",
        "........o.o...................o.o.o.....................o.o...................",
        ".......######..........e....##########.........e.................e...........",
        "..............................................................................",
        "......................................................................F.......",
        "######...######################...####################...####################",
    ]

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        w = max(len(r) for r in self.LEVEL)
        self.level = [r.ljust(w, ".") for r in self.LEVEL]
        self.ROWS_N, self.COLS_N = len(self.level), w
        self.setFixedSize(self.VIEW * self.TS, self.TOP + self.ROWS_N * self.TS)
        self.cat = cat_pixmap("supercat", 30)
        self.keys = set()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.new_game()

    def new_game(self):
        self.lives = 3
        self.coins = 0
        self.won = self.dead = self.paused = False
        self.got = set()
        self.enemies = []
        for ty, row in enumerate(self.level):
            for tx, ch in enumerate(row):
                if ch == "e":
                    gy = ty   # ищем пол под мышью
                    while gy + 1 < self.ROWS_N and self.level[gy + 1][tx] != "#":
                        gy += 1
                    self.enemies.append(dict(x=tx * self.TS, y=(gy + 1) * self.TS - self.EH,
                                             vx=1.4, dead=False))
        self.spawn()
        self.timer.start(16)
        self.update()

    def spawn(self):
        """Ставит кота в начало уровня (после потери жизни — тоже)."""
        self.px, self.py = 2 * self.TS, (self.ROWS_N - 2) * self.TS
        self.vx = self.vy = 0.0
        self.on_ground = True
        self.cam = 0.0

    def hideEvent(self, e):
        self.paused = True
        super().hideEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_R:
            self.new_game()
            e.accept()
            return
        self.keys.add(e.key())
        self.paused = False
        e.accept()

    def keyReleaseEvent(self, e):
        self.keys.discard(e.key())

    def rect_hit(self, x, y, w, h):
        """Пересекается ли прямоугольник с землёй."""
        x0, y0 = int(x // self.TS), int(y // self.TS)
        x1, y1 = int((x + w - 1) // self.TS), int((y + h - 1) // self.TS)
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                if 0 <= ty < self.ROWS_N and 0 <= tx < self.COLS_N \
                        and self.level[ty][tx] == "#":
                    return True
        return False

    def lose_life(self):
        self.lives -= 1
        if self.lives <= 0:
            self.dead = True
            self.timer.stop()
        else:
            self.spawn()

    def tick(self):
        if self.won or self.dead or self.paused:
            return
        left = self.keys & {Qt.Key.Key_Left, Qt.Key.Key_A}
        right = self.keys & {Qt.Key.Key_Right, Qt.Key.Key_D}
        jump = self.keys & {Qt.Key.Key_Up, Qt.Key.Key_W, Qt.Key.Key_Space}
        if self.on_ground and not self.rect_hit(self.px, self.py + self.PH, self.PW, 1):
            self.on_ground = False   # сошёл с края
        if not self.on_ground:
            self.vy = min(self.vy + self.GRAV, 12.0)
        nx = max(0.0, self.px + ((1 if right else 0) - (1 if left else 0)) * self.RUN)
        if not self.rect_hit(nx, self.py, self.PW, self.PH):
            self.px = nx
        if self.on_ground and jump:
            self.vy = self.JUMP
            self.on_ground = False
        if not self.on_ground:
            ny = self.py + self.vy
            if not self.rect_hit(self.px, ny, self.PW, self.PH):
                self.py = ny
            elif self.vy > 0:   # приземлились — ставим на верх клетки
                self.py = int((ny + self.PH) // self.TS) * self.TS - self.PH
                self.vy = 0.0
                self.on_ground = True
            else:               # упёрлись головой в потолок
                self.py = (int(ny // self.TS) + 1) * self.TS
                self.vy = 0.0

        for en in self.enemies:
            if en["dead"]:
                continue
            foot_tx = int((en["x"] + self.EW / 2 + (8 if en["vx"] > 0 else -8)) // self.TS)
            foot_ty = int((en["y"] + self.EH) // self.TS)
            ground_ahead = (0 <= foot_ty < self.ROWS_N and 0 <= foot_tx < self.COLS_N
                            and self.level[foot_ty][foot_tx] == "#")
            nx = en["x"] + en["vx"]
            if not ground_ahead or nx < 0 or self.rect_hit(nx, en["y"], self.EW, self.EH):
                en["vx"] = -en["vx"]
            else:
                en["x"] = nx
            if (self.px < en["x"] + self.EW and self.px + self.PW > en["x"]
                    and self.py < en["y"] + self.EH and self.py + self.PH > en["y"]):
                if self.vy > 0 and self.py + self.PH < en["y"] + self.EH * 0.7:
                    en["dead"] = True   # прыгнул сверху — мышь побеждена
                    self.vy = -8.0
                else:
                    self.lose_life()
                    return

        tx0, tx1 = int(self.px // self.TS), int((self.px + self.PW) // self.TS)
        ty0, ty1 = int(self.py // self.TS), int((self.py + self.PH) // self.TS)
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                if not (0 <= ty < self.ROWS_N and 0 <= tx < self.COLS_N):
                    continue
                ch = self.level[ty][tx]
                if ch == "o" and (tx, ty) not in self.got:
                    self.got.add((tx, ty))
                    self.coins += 1
                elif ch == "F":
                    self.won = True
                    self.timer.stop()
        if self.py > self.ROWS_N * self.TS + 40:   # упал в пропасть
            self.lose_life()
            return
        view = self.VIEW * self.TS
        self.cam = min(max(self.px - (view - self.PW) / 2, 0.0),
                       self.COLS_N * self.TS - view)
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
                   f'🪙 {self.coins}   ❤ {self.lives}')
        p.drawText(QRectF(self.width() / 2, 4, self.width() / 2 - 8, self.TOP - 8),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f'{tr("mario_hint")}   R — ⟳')

        cam = int(self.cam)
        tx0, tx1 = cam // self.TS, (cam + self.VIEW * self.TS) // self.TS + 1
        p.setPen(Qt.PenStyle.NoPen)
        for ty in range(self.ROWS_N):
            for tx in range(tx0, min(tx1 + 1, self.COLS_N)):
                ch = self.level[ty][tx]
                x, y = tx * self.TS - cam, self.TOP + ty * self.TS
                if ch == "#":
                    p.setBrush(QColor(P["input"]))
                    p.drawRoundedRect(QRectF(x + 1, y + 1, self.TS - 2, self.TS - 2), 4, 4)
                elif ch == "o" and (tx, ty) not in self.got:
                    p.setBrush(QColor("#eed49f"))
                    p.drawEllipse(QPointF(x + self.TS / 2, y + self.TS / 2),
                                  self.TS * 0.28, self.TS * 0.28)
                elif ch == "F":
                    p.setPen(QPen(QColor(P["dim"]), 3))
                    p.drawLine(int(x + self.TS / 2), int(y - 6),
                               int(x + self.TS / 2), int(y + self.TS))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(P["accent"]))
                    p.drawPolygon(QPolygonF([
                        QPointF(x + self.TS / 2, y - 6),
                        QPointF(x + self.TS / 2 + 16, y + 1),
                        QPointF(x + self.TS / 2, y + 8)]))

        for en in self.enemies:   # мыши: как в змейке — серые, с розовыми ушками
            if en["dead"]:
                continue
            x, y = en["x"] - cam, self.TOP + en["y"]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#a5adcb"))
            p.drawEllipse(QRectF(x + 4, y + 8, self.EW - 8, self.EH - 8))
            p.setBrush(QColor("#ed8796"))
            p.drawEllipse(QRectF(x + 4, y, 6, 8))
            p.drawEllipse(QRectF(x + self.EW - 10, y, 6, 8))
            p.setBrush(QColor("#2d2f3d"))
            p.drawEllipse(QRectF(x + 8, y + 10, 3, 4))
            p.drawEllipse(QRectF(x + self.EW - 11, y + 10, 3, 4))

        p.drawPixmap(int(self.px - cam) - 4, self.TOP + int(self.py) - 4, self.cat)

        if self.won or self.dead:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(QRectF(0, self.TOP, self.width(), self.height() - self.TOP), 8, 8)
            big = p.font()
            big.setBold(True)
            big.setPointSize(max(10, S["font_size"]))
            p.setFont(big)
            p.setPen(QColor("white"))
            if self.won:
                msg = f'{tr("win")}!\n🪙 {tr("coins")}: {self.coins}\n{tr("again")}'
            else:
                msg = f'{tr("game_over")}\n{tr("again")}'
            p.drawText(QRectF(0, self.TOP, self.width(), self.height() - self.TOP),
                       Qt.AlignmentFlag.AlignCenter, msg)
        p.end()


class KartGame(QWidget):
    """🏎 Котокарт — гонка по кольцу против двух котов-соперников.

    Управление: ↑ / W — газ, ←→ / A D — руль, ↓ / S — тормоз, R — заезд заново.
    Три круга; по траве карт едет медленно — не срезай.
    """

    W, FH = 640, 420
    TOP, BOTTOM = 34, 26
    N = 64          # точек в центральной линии трассы
    TRACK_W = 64    # ширина дороги
    LAPS = 3

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(self.W, self.TOP + self.FH + self.BOTTOM)
        self.pts = []
        cx, cy = self.W / 2, self.TOP + self.FH / 2
        rx, ry = self.W * 0.36, self.FH * 0.33
        for i in range(self.N):   # овал с неровностями — трасса не идеальный круг
            a = 2 * math.pi * i / self.N
            wob = 1 + 0.12 * math.sin(3 * a) + 0.07 * math.cos(5 * a)
            self.pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a)))
        self.keys = set()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.new_game()

    def new_game(self):
        self.over = self.paused = False
        self.player = self.kart(0, "#f5a97f")
        self.ais = [self.kart(4, "#8aadf4"), self.kart(8, "#a6da95")]
        for ai in self.ais:
            ai["speed"] = 1.0
        self.timer.start(16)
        self.update()

    def kart(self, idx, color):
        x, y = self.pts[idx % self.N]
        nx, ny = self.pts[(idx + 1) % self.N]
        return dict(x=x, y=y, a=math.atan2(ny - y, nx - x), speed=0.0,
                    cp=idx % self.N, lap=0, color=color)

    def hideEvent(self, e):
        self.paused = True
        super().hideEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_R:
            self.new_game()
            e.accept()
            return
        self.keys.add(e.key())
        self.paused = False
        e.accept()

    def keyReleaseEvent(self, e):
        self.keys.discard(e.key())

    def nearest(self, kart):
        best, bi = 1e9, 0
        for i, (x, y) in enumerate(self.pts):
            d = (x - kart["x"]) ** 2 + (y - kart["y"]) ** 2
            if d < best:
                best, bi = d, i
        return bi, math.sqrt(best)

    def on_road(self, kart):
        return self.nearest(kart)[1] <= self.TRACK_W / 2 + 6

    def progress(self, kart):
        ni = self.nearest(kart)[0]
        if kart["cp"] <= ni <= kart["cp"] + 6:   # едем вперёд по трассе
            kart["cp"] = ni
        if ni < 6 and kart["cp"] > self.N - 12:   # пересекли финишную черту
            kart["lap"] += 1
            kart["cp"] = 0

    def place(self):
        me = (self.player["lap"], self.player["cp"])
        return 1 + sum(1 for ai in self.ais if (ai["lap"], ai["cp"]) > me)

    def tick(self):
        if self.over or self.paused:
            return
        k = self.player
        gas = self.keys & {Qt.Key.Key_Up, Qt.Key.Key_W}
        brake = self.keys & {Qt.Key.Key_Down, Qt.Key.Key_S}
        left = self.keys & {Qt.Key.Key_Left, Qt.Key.Key_A}
        right = self.keys & {Qt.Key.Key_Right, Qt.Key.Key_D}
        vmax = 3.4 if self.on_road(k) else 1.5   # по траве — медленно
        if gas:
            k["speed"] = min(k["speed"] + 0.06, vmax)
        else:
            k["speed"] *= 0.985
        if brake:
            k["speed"] = max(0.0, k["speed"] - 0.12)
        k["a"] += ((1 if right else 0) - (1 if left else 0)) * 0.045 * min(1.0, k["speed"] / 2)
        k["x"] += math.cos(k["a"]) * k["speed"]
        k["y"] += math.sin(k["a"]) * k["speed"]
        self.progress(k)
        for ai in self.ais:   # соперники рулят к точке трассы чуть впереди
            tx, ty = self.pts[(ai["cp"] + 5) % self.N]
            want = math.atan2(ty - ai["y"], tx - ai["x"])
            d = (want - ai["a"] + math.pi) % (2 * math.pi) - math.pi
            ai["a"] += max(-0.06, min(0.06, d))
            ai["speed"] = min(ai["speed"] + 0.05, 2.9)
            ai["x"] += math.cos(ai["a"]) * ai["speed"]
            ai["y"] += math.sin(ai["a"]) * ai["speed"]
            self.progress(ai)
        if self.player["lap"] >= self.LAPS:
            self.over = True
            self.timer.stop()
        self.update()

    def paintEvent(self, _e):
        P = pal()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(P["panel"]))
        p.drawRect(self.rect())
        p.setBrush(QColor(P["bg"]))
        p.drawRoundedRect(QRectF(0, self.TOP, self.W, self.FH), 8, 8)

        hud = p.font()
        hud.setPointSize(max(8, S["font_size"] - 2))
        p.setFont(hud)
        p.setPen(QColor(P["dim"]))
        p.drawText(QRectF(8, 4, self.width() / 2, self.TOP - 8),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f'{tr("lap")}: {min(self.player["lap"] + 1, self.LAPS)}/{self.LAPS}'
                   f'   {tr("place")}: {self.place()}')
        p.drawText(QRectF(self.width() / 2, 4, self.width() / 2 - 8, self.TOP - 8),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "R — ⟳")

        road = QPainterPath()   # рисуем трассу толстой обводкой центральной линии
        road.moveTo(*self.pts[0])
        for x, y in self.pts[1:]:
            road.lineTo(x, y)
        road.closeSubpath()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(P["input"]), self.TRACK_W, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(road)
        center = QPen(QColor(P["dim"]), 2, Qt.PenStyle.SolidLine)
        center.setDashPattern([10, 12])
        p.setPen(center)
        p.drawPath(road)

        x0, y0 = self.pts[0]   # финишная черта — поперёк трассы
        x1, y1 = self.pts[1]
        dx, dy = x1 - x0, y1 - y0
        n = math.hypot(dx, dy) or 1.0
        px_, py_ = -dy / n, dx / n
        p.setPen(QPen(QColor("white"), 3))
        p.drawLine(QPointF(x0 + px_ * self.TRACK_W / 2, y0 + py_ * self.TRACK_W / 2),
                   QPointF(x0 - px_ * self.TRACK_W / 2, y0 - py_ * self.TRACK_W / 2))

        for kart in (*self.ais, self.player):
            p.save()
            p.translate(kart["x"], kart["y"])
            p.rotate(math.degrees(kart["a"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(kart["color"]))
            p.drawRoundedRect(QRectF(-14, -9, 28, 18), 5, 5)
            p.setBrush(QColor("white"))    # шлем кота-пилота
            p.drawEllipse(QPointF(2, 0), 4.5, 4.5)
            p.setBrush(QColor(P["text"]))
            p.drawEllipse(QPointF(4, -2), 1.2, 1.2)
            p.drawEllipse(QPointF(4, 2), 1.2, 1.2)
            p.restore()

        p.setPen(QColor(P["dim"]))
        p.drawText(QRectF(8, self.TOP + self.FH, self.width() - 16, self.BOTTOM - 6),
                   Qt.AlignmentFlag.AlignCenter, tr("kart_hint"))

        if self.over or self.paused:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(QRectF(0, self.TOP, self.W, self.FH), 8, 8)
            big = p.font()
            big.setBold(True)
            big.setPointSize(max(10, S["font_size"]))
            p.setFont(big)
            p.setPen(QColor("white"))
            if self.over:
                msg = (tr("win") + "!") if self.place() == 1 else \
                    f'{tr("place")}: {self.place()}'
                msg += f'\n{tr("again")}'
            else:
                msg = tr("paused")
            p.drawText(QRectF(0, self.TOP, self.W, self.FH),
                       Qt.AlignmentFlag.AlignCenter, msg)
        p.end()


class ArkanoidGame(QWidget):
    """🧱 Котаноид — отбивай мяч ракеткой, разбей все кирпичи.

    Управление: мышь или ←→ / A D, R — заново. Три жизни.
    """

    W, FH = 500, 340
    TOP, BOTTOM = 34, 26
    COLS_BR, ROWS_BR = 10, 5
    BR_W, BR_H = 45, 18
    BR_COLORS = ["#8aadf4", "#a6da95", "#eed49f", "#f5a97f", "#c6a0f6"]
    PAD_W, PAD_H = 76, 12
    R = 6

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setFixedSize(self.W, self.TOP + self.FH + self.BOTTOM)
        self.keys = set()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.new_game()

    def new_game(self):
        self.lives = 3
        self.won = self.dead = self.paused = False
        self.bricks = []
        for row in range(self.ROWS_BR):
            for col in range(self.COLS_BR):
                self.bricks.append(dict(x=5 + col * (self.BR_W + 4),
                                        y=self.TOP + 10 + row * (self.BR_H + 4),
                                        color=self.BR_COLORS[row], dead=False))
        self.pad_x = (self.W - self.PAD_W) / 2
        self.serve()
        self.timer.start(16)
        self.update()

    def serve(self):
        """Мяч над ракеткой, летит вверх под случайным углом."""
        self.bx = self.W / 2
        self.by = self.TOP + self.FH - 40
        self.vx = random.uniform(-2.0, 2.0)
        self.vy = -3.2

    def hideEvent(self, e):
        self.paused = True
        super().hideEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_R:
            self.new_game()
            e.accept()
            return
        self.keys.add(e.key())
        self.paused = False
        e.accept()

    def keyReleaseEvent(self, e):
        self.keys.discard(e.key())

    def mouseMoveEvent(self, e):
        if not (self.won or self.dead or self.paused):
            self.pad_x = min(max(e.position().x() - self.PAD_W / 2, 0.0),
                             self.W - self.PAD_W)

    def tick(self):
        if self.won or self.dead or self.paused:
            return
        left = self.keys & {Qt.Key.Key_Left, Qt.Key.Key_A}
        right = self.keys & {Qt.Key.Key_Right, Qt.Key.Key_D}
        if left:
            self.pad_x = max(0.0, self.pad_x - 6)
        if right:
            self.pad_x = min(self.pad_x + 6, self.W - self.PAD_W)
        self.bx += self.vx
        self.by += self.vy
        if self.bx < self.R:                 # стены
            self.bx = self.R
            self.vx = abs(self.vx)
        elif self.bx > self.W - self.R:
            self.bx = self.W - self.R
            self.vx = -abs(self.vx)
        if self.by < self.TOP + self.R:
            self.by = self.TOP + self.R
            self.vy = abs(self.vy)
        pad_y = self.TOP + self.FH - 16
        if (self.vy > 0 and self.by + self.R >= pad_y
                and self.by + self.R <= pad_y + self.PAD_H + 6
                and self.pad_x <= self.bx + self.R and self.bx - self.R <= self.pad_x + self.PAD_W):
            self.vy = -abs(self.vy)   # угол отскока зависит от точки удара
            self.vx = max(-4.0, min(4.0, self.vx + (self.bx - (self.pad_x + self.PAD_W / 2)) * 0.06))
        for br in self.bricks:
            if br["dead"]:
                continue
            if (self.bx + self.R > br["x"] and self.bx - self.R < br["x"] + self.BR_W
                    and self.by + self.R > br["y"] and self.by - self.R < br["y"] + self.BR_H):
                br["dead"] = True
                if self.bx >= br["x"] and self.bx <= br["x"] + self.BR_W:
                    self.vy = -self.vy
                else:
                    self.vx = -self.vx
                break
        if all(br.get("dead") for br in self.bricks):
            self.won = True
            self.timer.stop()
        if self.by > self.TOP + self.FH + self.R:   # мяч улетел вниз
            self.lives -= 1
            if self.lives <= 0:
                self.dead = True
                self.timer.stop()
            else:
                self.serve()
        self.update()

    def paintEvent(self, _e):
        P = pal()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(P["panel"]))
        p.drawRect(self.rect())
        p.setBrush(QColor(P["bg"]))
        p.drawRoundedRect(QRectF(0, self.TOP, self.W, self.FH), 8, 8)

        hud = p.font()
        hud.setPointSize(max(8, S["font_size"] - 2))
        p.setFont(hud)
        p.setPen(QColor(P["dim"]))
        p.drawText(QRectF(8, 4, self.width() / 2, self.TOP - 8),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f'❤ {self.lives}')
        p.drawText(QRectF(self.width() / 2, 4, self.width() / 2 - 8, self.TOP - 8),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "R — ⟳")

        for br in self.bricks:
            if br.get("dead"):
                continue
            p.setBrush(QColor(br["color"]))
            p.drawRoundedRect(QRectF(br["x"], br["y"], self.BR_W, self.BR_H), 4, 4)
        p.setBrush(QColor(P["accent"]))
        p.drawRoundedRect(QRectF(self.pad_x, self.TOP + self.FH - 16,
                                 self.PAD_W, self.PAD_H), 6, 6)
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(self.bx, self.by), self.R, self.R)

        p.setPen(QColor(P["dim"]))
        p.drawText(QRectF(8, self.TOP + self.FH, self.width() - 16, self.BOTTOM - 6),
                   Qt.AlignmentFlag.AlignCenter, tr("arka_hint"))

        if self.won or self.dead or self.paused:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(QRectF(0, self.TOP, self.W, self.FH), 8, 8)
            big = p.font()
            big.setBold(True)
            big.setPointSize(max(10, S["font_size"]))
            p.setFont(big)
            p.setPen(QColor("white"))
            if self.won:
                msg = f'{tr("win")}!\n{tr("again")}'
            elif self.dead:
                msg = f'{tr("game_over")}\n{tr("again")}'
            else:
                msg = tr("paused")
            p.drawText(QRectF(0, self.TOP, self.W, self.FH),
                       Qt.AlignmentFlag.AlignCenter, msg)
        p.end()


class GameScaleView(QGraphicsView):
    """Растягивает игру с фиксированной сеткой на всё доступное место.

    Игры рисуют поле в «пикселях» своей сетки и имеют setFixedSize; чтобы окно
    можно было разтянуть на весь экран, оборачиваем игру в графическую сцену
    и масштабируем её целиком с сохранением пропорций: окно растянули —
    растянулась и игра. Клики и клавиши проходят сквозь масштаб.
    """

    def __init__(self, game):
        super().__init__()
        self.game = game
        self._scene = QGraphicsScene(self)
        self._scene.addWidget(game)   # попадёт в QGraphicsProxyWidget
        self._scene.setSceneRect(0, 0, game.width(), game.height())
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform
                            | QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fitInView(self._scene.sceneRect(),
                       Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, e):
        # клик мимо самой игры (по фону) — всё равно даём игре клавиатуру
        self.game.setFocus()
        super().mousePressEvent(e)


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
        self.resize(820, 640)   # растягивается мышью как угодно дальше
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


class TanksGame(QWidget):
    """Танки: дуэль на двоих за одной клавиатурой (hot-seat).

    Игрок 1 — WASD + Space, игрок 2 — стрелки + Enter. Пули летают по прямой,
    ломают кирпичи; попадание в танк — очко стрелявшему, подбитый возрождается
    на своей базе через секунду. R — новая партия.
    """

    CELL = 46
    W, H = 15, 11
    TOP = 34
    DIRS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(self.W * self.CELL, self.TOP + self.H * self.CELL)
        self.keys = set()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.new_game()

    def new_game(self):
        rnd = random.Random()
        self.grid = [["#"] * self.W for _ in range(self.H)]
        for y in range(1, self.H - 1):
            for x in range(1, self.W - 1):
                self.grid[y][x] = " "
        for _ in range(12):     # стальные колонны — пуля их не берёт
            self.grid[rnd.randrange(2, self.H - 2)][rnd.randrange(2, self.W - 2)] = "#"
        for _ in range(30):     # кирпичи — их пули ломают
            x, y = rnd.randrange(1, self.W - 1), rnd.randrange(1, self.H - 1)
            if self.grid[y][x] == " ":
                self.grid[y][x] = "x"
        for cx, cy in ((1, self.H - 2), (self.W - 2, 1)):   # базы — всегда чистые
            for yy in range(cy - 1, cy + 2):
                for xx in range(cx - 1, cx + 2):
                    if 1 <= yy < self.H - 1 and 1 <= xx < self.W - 1:
                        self.grid[yy][xx] = " "
        self.tanks = [
            {"x": self.px(1), "y": self.py(self.H - 2), "d": "U", "cool": 0, "dead": 0,
             "spawn": (self.px(1), self.py(self.H - 2)), "hue": "out"},
            {"x": self.px(self.W - 2), "y": self.py(1), "d": "D", "cool": 0, "dead": 0,
             "spawn": (self.px(self.W - 2), self.py(1)), "hue": "inn"},
        ]
        self.score = [0, 0]
        self.bullets = []
        self.keys.clear()
        self.timer.start(16)

    def px(self, cx):
        return cx * self.CELL + 6

    def py(self, cy):
        return cy * self.CELL + 6

    def free(self, x, y, i):
        """Может ли танк i встать в точку (x, y): стены и другие танки мешают."""
        w = self.CELL - 12
        x0, y0 = int(x // self.CELL), int(y // self.CELL)
        x1, y1 = int((x + w - 1) // self.CELL), int((y + w - 1) // self.CELL)
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                if not (0 <= ty < self.H and 0 <= tx < self.W):
                    return False
                if self.grid[ty][tx] != " ":
                    return False
        for j, t in enumerate(self.tanks):
            if j != i and t["dead"] == 0 and x < t["x"] + w and t["x"] < x + w \
                    and y < t["y"] + w and t["y"] < y + w:
                return False
        return True

    def control(self, i, up, down, left, right, fire):
        t = self.tanks[i]
        if t["dead"] > 0:
            return
        if fire in self.keys and t["cool"] == 0:
            dx, dy = self.DIRS[t["d"]]
            cx, cy = t["x"] + (self.CELL - 12) / 2, t["y"] + (self.CELL - 12) / 2
            self.bullets.append({"x": cx + dx * 12 - 2, "y": cy + dy * 12 - 2,
                                 "dx": dx, "dy": dy, "o": i})
            t["cool"] = 18
        t["cool"] = max(0, t["cool"] - 1)
        for key, d in ((up, "U"), (down, "D"), (left, "L"), (right, "R")):
            if key in self.keys:
                t["d"] = d
                dx, dy = self.DIRS[d]
                if self.free(t["x"] + dx * 3, t["y"] + dy * 3, i):
                    t["x"] += dx * 3
                    t["y"] += dy * 3
                break

    def tick(self):
        self.control(0, Qt.Key.Key_W, Qt.Key.Key_S, Qt.Key.Key_A, Qt.Key.Key_D,
                     Qt.Key.Key_Space)
        self.control(1, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left,
                     Qt.Key.Key_Right, Qt.Key.Key_Return)
        alive = []
        for b in self.bullets:
            hit = None
            for _step in range(2):     # пуля в два раза быстрее танка
                b["x"] += b["dx"] * 3
                b["y"] += b["dy"] * 3
                cx, cy = int((b["x"] + 2) // self.CELL), int((b["y"] + 2) // self.CELL)
                if not (0 <= cy < self.H and 0 <= cx < self.W) \
                        or self.grid[cy][cx] == "#":
                    hit = "#"
                elif self.grid[cy][cx] == "x":
                    self.grid[cy][cx] = " "   # кирпич разлетается
                    hit = "x"
                else:
                    w = self.CELL - 12
                    for j, t in enumerate(self.tanks):
                        if t["dead"] == 0 and j != b["o"] \
                                and b["x"] + 4 > t["x"] and b["x"] < t["x"] + w \
                                and b["y"] + 4 > t["y"] and b["y"] < t["y"] + w:
                            hit = "tank"
                            t["dead"] = 60
                            self.score[b["o"]] += 1
                            break
                if hit:
                    break
            if not hit:
                alive.append(b)
        self.bullets = alive
        for t in self.tanks:
            if t["dead"] > 0:
                t["dead"] -= 1
                if t["dead"] == 0:
                    t["x"], t["y"] = t["spawn"]
                    t["d"] = "U" if t["hue"] == "out" else "D"
        self.update()

    def paintEvent(self, e):
        P = pal()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(P["bg"]))
        f = p.font()
        f.setPointSize(max(8, S["font_size"] - 2))
        p.setFont(f)
        p.setPen(QColor(P["dim"]))
        p.drawText(QRectF(0, 0, self.width(), self.TOP - 4),
                   Qt.AlignmentFlag.AlignCenter,
                   f'🟠 {self.score[0]} : {self.score[1]} 🔵   (WASD+Space / ⌨+Enter, R)')
        for y in range(self.H):
            for x in range(self.W):
                c = self.grid[y][x]
                if c == " ":
                    continue
                rx, ry = x * self.CELL, self.TOP + y * self.CELL
                if c == "#":
                    p.fillRect(QRectF(rx + 1, ry + 1, self.CELL - 2, self.CELL - 2),
                               QColor(P["panel"]))
                    p.setPen(QColor(P["border"]))
                    p.drawRect(QRectF(rx + 1.5, ry + 1.5, self.CELL - 3, self.CELL - 3))
                else:
                    p.fillRect(QRectF(rx + 2, ry + 2, self.CELL - 4, self.CELL - 4),
                               QColor(P["input"]))
        w = self.CELL - 12
        for i, t in enumerate(self.tanks):
            if t["dead"] > 0:
                continue
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(P[t["hue"]]))
            p.drawRoundedRect(QRectF(t["x"], t["y"], w, w), 6, 6)
            dx, dy = self.DIRS[t["d"]]
            cx, cy = t["x"] + w / 2, t["y"] + w / 2
            p.setPen(QPen(QColor(P["bg"]), 5, Qt.PenStyle.SolidLine))
            p.drawLine(QPointF(cx, cy), QPointF(cx + dx * w * 0.7, cy + dy * w * 0.7))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(P["text"]))
        for b in self.bullets:
            p.drawEllipse(QPointF(b["x"] + 2, b["y"] + 2), 3.0, 3.0)
        p.end()

    def hideEvent(self, e):
        self.timer.stop()
        self.keys.clear()
        super().hideEvent(e)

    def showEvent(self, e):
        self.timer.start(16)
        self.setFocus()
        super().showEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_R:
            self.new_game()
            e.accept()
            return
        self.keys.add(e.key())
        e.accept()

    def keyReleaseEvent(self, e):
        self.keys.discard(e.key())
        e.accept()


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


def translate_text(text, to_lang):
    """Перевод текста публичным endpoint Google Translate (ключ не нужен)."""
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx"
           f"&sl=auto&tl={to_lang}&dt=t&q={urllib.parse.quote(text)}")
    req = urllib.request.Request(url, headers={"User-Agent": f"catgram/{VERSION}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    return "".join(seg[0] for seg in data[0] if seg and seg[0])


def tg_lang():
    """Код языка переводчика: цель выбирается в настройках, по умолчанию — язык интерфейса."""
    code = S.get("tr_lang") or S["lang"]
    return {"zh": "zh-CN"}.get(code, code)


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


# ---------- шумоподавление ----------

NOISE_MARK = "catgram_noise"          # метка виртуальных устройств на время звонка
NOISE_MIC = "catgram_noise_mic"       # «чистый» микрофон (module-echo-cancel)
NOISE_SINK = "catgram_noise_sink"     # виртуальный динамик (AEC вычитает его из микрофона)
NOISE_RN = "catgram_noise_rnnoise"   # «чистый» микрофон (RNNoise, мощный шумодав)
NOISE_NAMES = {   # как показывать выбранный способ в строке состояния
    "rnnoise+aec": "RNNoise + WebRTC AEC",
    "rnnoise": "RNNoise",
    "webrtc": "WebRTC AEC",
    "speex": "Speex AEC",
}

# Конфиг filter-chain PipeWire: RNNoise через LADSPA-плагин librnnoise_ladspa.
# «pipewire -c <конфиг>» стартует клиентский узел к работающему серверу:
# обычный микрофон -> RNNoise (нейросетевой шумодав) -> новый источник.
# %%PLUGIN%% заменяем на имя плагина — с «.so» и без (дистрибутивы вольно
# называют библиотеку, dlopen суффикс сам не добавляет).
NOISE_RN_CONF = """context.modules = [
{ name = libpipewire-module-filter-chain
  args = {
    node.description = "catgram noise (rnnoise)"
    media.name = "catgram noise"
    filter.chain = [
      { type = ladspa plugin = %%PLUGIN%% label = noise_suppressor_control }
    ]
    capture.props = { node.name = catgram_noise_capture node.passive = true }
    playback.props = { node.name = catgram_noise_rnnoise media.class = "Audio/Source" }
  }
}
]
"""


def find_pactl():
    """pactl есть не всегда: в nix-shell его может не быть в PATH.

    Ищем в PATH и в системных путях NixOS/обычных дистрибутивов; None —
    не нашли (останется RNNoise без AEC или pw-dump-режим).
    """
    pactl = shutil.which("pactl")
    if pactl:
        return pactl
    for p in ("/run/current-system/sw/bin/pactl",
              "/usr/bin/pactl", "/usr/local/bin/pactl"):
        if os.access(p, os.X_OK):
            return p
    return None


def noise_list(pactl, kind):
    """pactl list short sources/sinks — вывод списком строк."""
    try:
        r = subprocess.run([pactl, "list", "short", kind],
                           capture_output=True, timeout=5)
        return r.stdout.decode(errors="replace").splitlines()
    except Exception:
        return []


def sources_text(pactl, pw_dump):
    """Текст со списком всех источников — ищем в нём имя виртуального микрофона.

    pactl — в nix-shell может отсутствовать; тогда берём pw-dump (он всегда
    в комплекте с pipewire) и ищем имя источника прямо в его JSON.
    """
    if pactl:
        try:
            r = subprocess.run([pactl, "list", "short", "sources"],
                               capture_output=True, timeout=5)
            return r.stdout.decode(errors="replace")
        except Exception:
            return ""
    if pw_dump:
        try:
            r = subprocess.run([pw_dump], capture_output=True, timeout=8)
            return r.stdout.decode(errors="replace")
        except Exception:
            return ""
    return ""


def rnnoise_env():
    """LADSPA_PATH для дочернего pipewire: filter-chain грузит плагин в нём самом.

    На NixOS библиотека лежит в /nix/store (nix-shell -p rnnoise-plugin) или
    в /run/current-system/sw/lib/ladspa (environment.systemPackages) — pipewire
    сам её не найдёт, подсунем путь явно. None — пусть ищет по своим правилам.
    """
    dirs = [d for d in os.environ.get("LADSPA_PATH", "").split(":") if d]
    for d in ("/run/current-system/sw/lib/ladspa",
              "/usr/lib/ladspa", "/usr/lib64/ladspa",
              "/usr/local/lib/ladspa", "/usr/lib/x86_64-linux-gnu/ladspa"):
        if Path(d).is_dir() and d not in dirs:
            dirs.append(d)
    try:   # nix-shell -p pipewire rnnoise-plugin: плагин в /nix/store, а не в системе
        for d in glob.glob("/nix/store/*rnnoise*/lib/ladspa"):
            if Path(d).is_dir() and d not in dirs:
                dirs.append(d)
    except Exception:
        pass
    if not dirs:
        return None
    env = dict(os.environ)
    env["LADSPA_PATH"] = ":".join(dirs)
    return env


def start_rnnoise(pactl, pw_dump):
    """Поднимает RNNoise через filter-chain PipeWire.

    Возвращаем (процесс pipewire, None) или (None, причина). Процесс надо
    держать живым до конца звонка и прибить после (disable_noise_suppression).
    Пробуем оба имени плагина: с «.so» и без.
    """
    pipewire = shutil.which("pipewire")
    if not pipewire:
        return None, "pipewire not found"
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return None, f"cache dir failed: {e}"
    env = rnnoise_env()
    err = None
    for plugin in ("librnnoise_ladspa.so", "librnnoise_ladspa"):
        conf = CACHE_DIR / "catgram-noise.conf"
        try:
            conf.write_text(NOISE_RN_CONF.replace("%%PLUGIN%%", plugin))
        except OSError as e:
            return None, f"rnnoise config write failed: {e}"
        try:
            kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            if env:
                kw["env"] = env
            proc = subprocess.Popen([pipewire, "-c", str(conf)], **kw)
        except Exception as e:
            return None, f"pipewire launch failed: {e}"
        visible, exited = False, None
        for _ in range(16):   # ждём, пока сервер опубликует виртуальный источник
            if NOISE_RN in sources_text(pactl, pw_dump):
                visible = True
                break
            if proc.poll() is not None:
                exited = f"pipewire exited ({plugin} not loadable?)"
                break
            time.sleep(0.25)
        if visible:
            return proc, None
        err = exited or "rnnoise source not visible (filter-chain failed)"
        proc.terminate()
        try:
            proc.wait(2)
        except Exception:
            proc.kill()
    return None, err or "rnnoise not available"


def load_echo_cancel(run, method="webrtc", source_master=None):
    """Грузит module-echo-cancel; (индекс, None) или (None, причина)."""
    args = ["load-module", "module-echo-cancel", "aec_method=" + method,
            "source_name=" + NOISE_MIC, "sink_name=" + NOISE_SINK]
    if source_master:   # берём звук не с обычного микрофона, а с rnnoise-источника
        args.append("source_master=" + source_master)
    try:
        r = run(*args)
    except Exception as e:
        return None, str(e)
    if r.returncode != 0 or not r.stdout.strip():
        return None, (r.stderr.decode(errors="replace").strip()
                      or f"load-module failed ({method})").splitlines()[-1]
    try:
        return int(r.stdout.decode().strip().splitlines()[-1]), None
    except (ValueError, IndexError):
        return None, "bad module index"


def enable_noise_suppression():
    """Собирает «чистый» микрофон для звонка, от лучшего к худшему.

    1) RNNoise (нейросетевой шумодав) через filter-chain PipeWire + сверху
       module-echo-cancel с webrtc — эхо динамика тоже вычитается;
    2) RNNoise без echo-cancel (эхо уберёт сам движок звонка);
    3) module-echo-cancel с webrtc (шумодав послабее, встроен в webrtc AEC);
    4) module-echo-cancel со speex — на случай сборки без webrtc.

    Возвращаем dict: method («rnnoise+aec»/«rnnoise»/«webrtc»/«speex»/None),
    module (индекс module-echo-cancel), proc (процесс pipewire), err (причина).
    """
    pactl = find_pactl()
    pw_dump = shutil.which("pw-dump")   # в комплекте с pipewire
    if not pactl and not pw_dump:
        return {"method": None, "module": None, "proc": None,
                "err": "pactl and pw-dump not found (PulseAudio/PipeWire not installed?)"}

    def run(*args):
        return subprocess.run([pactl, *args], capture_output=True, timeout=5)

    if pactl:
        for idx in stale_noise_modules():   # после падения catgram модуль мог остаться
            try:
                run("unload-module", str(idx))
            except Exception:
                pass

    # 1) RNNoise — самое мощное шумоподавление (pactl не нужен)
    proc, err = start_rnnoise(pactl, pw_dump)
    if proc is not None:
        if pactl:   # эхо сверху — только через pulse-модуль, то есть через pactl
            idx, aec_err = load_echo_cancel(run, "webrtc", source_master=NOISE_RN)
            if idx is not None and noise_devices_ready(pactl):
                return {"method": "rnnoise+aec", "module": idx, "proc": proc, "err": None}
            if idx is not None:   # поднялся, но устройств не дал — выгружаем
                try:
                    run("unload-module", str(idx))
                except Exception:
                    pass
            elif aec_err:   # поверх RNNoise эхо не прикрутилось — ну и ладно
                err = aec_err
        return {"method": "rnnoise", "module": None, "proc": proc, "err": None}

    # 2) без RNNoise — хотя бы AEC со встроенным шумодавом (для него нужен pactl)
    if not pactl:
        return {"method": None, "module": None, "proc": None,
                "err": f"rnnoise: {err or 'no'}; pactl not found (AEC unavailable)"}
    last = err or ""
    for method in ("webrtc", "speex"):
        idx, m_err = load_echo_cancel(run, method)
        if idx is not None and noise_devices_ready(pactl):
            # работает, но RNNoise не поднялся — сохраним причину для «Проверить»
            return {"method": method, "module": idx, "proc": None,
                    "err": f"rnnoise: {err}" if err else None}
        if idx is not None:
            try:
                run("unload-module", str(idx))
            except Exception:
                pass
        last = f"{method}: {m_err}" if m_err else "virtual device not visible"
    return {"method": None, "module": None, "proc": None,
            "err": f"rnnoise: {err or 'no'}; echo-cancel: {last}"}


def noise_devices_ready(pactl):
    """Появились ли виртуальные источник и sink: модуль может «подняться»,
    а устройства при этом не создаться (нет прав, конфликт сессии и т.п.)."""
    try:
        src = subprocess.run([pactl, "list", "short", "sources"],
                             capture_output=True, timeout=5)
        snk = subprocess.run([pactl, "list", "short", "sinks"],
                             capture_output=True, timeout=5)
        return (NOISE_MIC.encode() in src.stdout
                and NOISE_SINK.encode() in snk.stdout)
    except Exception:
        return False


def stale_noise_modules():
    """Индексы module-echo-cancel, оставшихся от прошлых запусков catgram."""
    pactl = find_pactl()
    if not pactl:
        return []
    try:
        r = subprocess.run([pactl, "list", "short", "modules"],
                           capture_output=True, timeout=5)
        return [int(line.split("\t")[0])
                for line in r.stdout.decode(errors="replace").splitlines()
                if "module-echo-cancel" in line and NOISE_MARK in line]
    except Exception:
        return []


def disable_noise_suppression(state):
    """Выгружает всё, что поднял enable_noise_suppression().

    Словарь состояния: module — индекс module-echo-cancel, proc — процесс
    pipewire с RNNoise. Любая часть может отсутствовать — приберём что есть.
    """
    if not state:
        return
    pactl = find_pactl()
    if pactl and state.get("module") is not None:
        try:
            subprocess.run([pactl, "unload-module", str(state["module"])],
                           capture_output=True, timeout=5)
        except Exception:
            pass
    proc = state.get("proc")
    if proc is not None:
        try:
            proc.terminate()
            try:
                proc.wait(3)
            except Exception:
                proc.kill()
        except Exception:
            pass


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
        self.noise = None    # состояние шумоподавления (см. enable_noise_suppression)
        self.noise_err = None   # почему шумоподавление не заработало (для строки состояния)

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

    async def start_noise(self):
        """Поднимает шумоподавление на время звонка; True — работает.

        Способ зависит от системы: RNNoise + WebRTC AEC, RNNoise, WebRTC AEC
        или Speex — какой первым поднялся (enable_noise_suppression возвращает
        словарь с выбранным способом; показываем его в строке состояния).
        """
        if self.noise is None:
            st = await asyncio.to_thread(enable_noise_suppression)
            if st["method"]:
                self.noise = st
                self.win.statusBar().showMessage(
                    tr("noise_on").format(name=NOISE_NAMES[st["method"]]), 6000)
            else:
                self.noise_err = st["err"]
        return self.noise is not None

    async def media(self):
        """Что отправляем в линию: микрофон — по возможности с шумоподавлением.

        ntgcalls сам берёт звук с устройства и не умеет шумоподавление, поэтому
        перед звонком просим PulseAudio/PipeWire собрать виртуальный источник с
        webrtc-AEC (убирает фоновый шум и эхо динамика) и берём его.
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
        mic = devs.microphone[0].metadata
        if S["noise_suppression"]:
            if await self.start_noise():
                try:   # шумодав поднялся — ищем в свежем списке его «чистый» микрофон
                    fresh = await _run(self.ntg.get_media_devices)
                    mics = [d.metadata for d in fresh.microphone]
                    best = next((m for m in mics if NOISE_MIC in str(m).lower()), None)
                    if best is None:   # rnnoise без AEC — берём его источник
                        best = next((m for m in mics
                                     if NOISE_MARK in str(m).lower()
                                     or "echo-cancel" in str(m).lower()), None)
                    if best is not None:
                        mic = best
                    else:   # шумодав есть, а ntgcalls устройство не видит — скажем об этом
                        self.win.statusBar().showMessage(
                            f'{tr("noise_off")}: catgram_noise devices not in list', 8000)
                except Exception:
                    pass
            else:   # шумоподавление не поднялось — говорим, почему, и звоним как есть
                self.win.statusBar().showMessage(
                    f'{tr("noise_off")}: {self.noise_err}', 8000)
        return ntgcalls.MediaDescription(
            microphone=ntgcalls.AudioDescription(
                media_source=ntgcalls.MediaSource.DEVICE, input=mic,
                sample_rate=CALL_RATE, channel_count=1, keep_open=False),
            speaker=None, camera=None, screen=None)

    async def playback_media(self):
        """Где слушаем собеседника.

        Особенность ntgcalls: входящий звук выдаётся в слот microphone описания
        PLAYBACK (внутри это addTrack(Playback, Microphone)), поэтому туда
        попадает устройство динамиков — это не опечатка.
        Если включено шумоподавление — играем в виртуальный sink: AEC вычтет
        этот звук из микрофона, и собеседник не услышит сам себя.
        """
        try:
            devs = await _run(self.ntg.get_media_devices)
        except Exception as e:
            raise RuntimeError(f"{tr('call_no_audio')}\n\n"
                               f"{tr('call_hint_throw').format(err=e)}\n"
                               f"{tr('call_hint_server')}") from e
        if not devs.speaker:
            raise RuntimeError(f"{tr('call_no_audio')}\n\n{audio_hints(devs, 'spk')}")
        spk = devs.speaker[0].metadata
        if self.noise is not None and self.noise.get("module") is not None:
            # есть module-echo-cancel: играем в его виртуальный sink, чтобы
            # AEC вычтет этот звук из микрофона (собеседник не услышит сам себя).
            # В режиме rnnoise без AEC эхо уберёт сам движок звонка.
            try:
                fresh = await _run(self.ntg.get_media_devices)
                spks = [d.metadata for d in fresh.speaker]
                best = next((s for s in spks if NOISE_SINK in str(s).lower()), None)
                if best is None:
                    best = next((s for s in spks
                                 if NOISE_MARK in str(s).lower()
                                 or "echo-cancel" in str(s).lower()), None)
                if best is not None:
                    spk = best
            except Exception:
                pass
        return ntgcalls.MediaDescription(
            microphone=ntgcalls.AudioDescription(
                media_source=ntgcalls.MediaSource.DEVICE, input=spk,
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
        if self.noise is not None:   # выгружаем шумоподавление (модуль + rnnoise)
            st, self.noise = self.noise, None
            try:
                await asyncio.to_thread(disable_noise_suppression, st)
            except Exception:
                pass
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
        self.client.flood_sleep_threshold = 120   # мелкие flood-wait ждём сами, без падений
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
        self.translating = set()  # id чатов, где включён автоперевод
        self.translations = {}   # (id чата, id сообщения) -> перевод
        self.reply_to = None     # id сообщения, на которое отвечаем (reply)
        self.chat_photos = {}    # id чата -> {id сообщения: ключ catimg:...} для просмотрщика
        self.last_day = None     # дата последнего показанного сообщения: разделители дней
        self.oldest_id = None    # id самого старого загруженного сообщения открытого чата
        self.history_done = False   # дошли до начала переписки
        self.paging = False      # подгрузка вверх разрешена (первая страница уже показана)
        self.older_busy = None   # «поколение», для которого сейчас идёт подгрузка вверх
        self.epoch = 0           # номер «поколения» окна: ответы для прошлого чата отбрасываются
        self._tasks = set()
        self.sticker_panel = None   # панель стикеров (создаётся лениво, переживает закрытия)
        self.calls = Calls(self)    # голосовые звонки

        self.setWindowIcon(QIcon(cat_pixmap("catgram", 128)))
        # трей есть не везде: в nix-shell без StatusNotifier QDBusTrayIcon сыпал бы
        # ошибками D-Bus (org.freedesktop.DBus.Error.ServiceUnknown) — в такой
        # среде уведомления просто не создаются
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QIcon(cat_pixmap("catgram", 128)), self)   # уведомления
            self.tray.show()
            self.tray.messageClicked.connect(self.on_notify_click)
        self.last_notify = None   # чат последнего уведомления: клик откроет его
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
        self.game_btn = QPushButton("🎮")   # «Играть»: мини-приложение бота
        self.game_btn.clicked.connect(self.on_bot_app)
        self.game_btn.hide()
        self.reply_lbl = QLabel()   # «ответ на сообщение» над полем ввода (как в TG Desktop)
        self.reply_lbl.hide()

        self.info_panel = QWidget()   # третья колонка: профиль собеседника
        self.info_panel.hide()
        self.info_panel.setMinimumWidth(250)
        self.info_avatar = QLabel()
        self.info_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_title = QLabel()
        self.info_title.setWordWrap(True)
        bold = self.info_title.font()
        bold.setBold(True)
        self.info_title.setFont(bold)
        self.info_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_user = QLabel()
        self.info_user.setWordWrap(True)
        self.info_phone = QLabel()
        self.info_phone.setWordWrap(True)
        self.info_about = QLabel()
        self.info_about.setWordWrap(True)
        self.info_members = QLabel()
        self.info_members.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_media_btn = QPushButton()
        self.info_media_btn.clicked.connect(self.open_media_search)
        ip = QVBoxLayout(self.info_panel)
        ip.setContentsMargins(10, 14, 10, 10)
        ip.setSpacing(6)
        ip.addWidget(self.info_avatar)
        ip.addWidget(self.info_title)
        ip.addWidget(self.info_user)
        ip.addWidget(self.info_phone)
        ip.addWidget(self.info_about)
        ip.addWidget(self.info_members)
        ip.addStretch(1)
        ip.addWidget(self.info_media_btn)

        self.info_btn = QPushButton("ℹ")   # показать/спрятать панель профиля
        self.info_btn.setFixedWidth(36)
        self.info_btn.clicked.connect(self.toggle_info)
        head_row = QHBoxLayout()
        head_row.setSpacing(6)
        head_row.addWidget(self.header, 1)
        head_row.addWidget(self.info_btn)
        head_row.addWidget(self.call_btn)
        head_row.addWidget(self.tel_btn)
        head_row.addWidget(self.game_btn)

        self.view = ChatView(self.photo_cache)
        self.view.setObjectName("chat_view")   # чтобы QSS мог дать ему обои
        self.view.anchorClicked.connect(self.on_anchor)   # http — в браузер, catvid: — видео
        self.view.msgCtx.connect(self.msg_ctx)   # правый клик по сообщению
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
        self.tr_btn = QPushButton("🌐")   # перевод того, что ты пишешь
        self.tr_btn.clicked.connect(self.on_translate_input)
        self.send_btn = QPushButton()   # кот на кнопке отправки
        self.send_btn.setIcon(QIcon(cat_pixmap("send", 32)))
        self.send_btn.setFixedSize(44, 34)
        self.send_btn.clicked.connect(self.on_send)
        send_row = QHBoxLayout()
        send_row.setSpacing(6)
        send_row.addWidget(self.attach)
        send_row.addWidget(self.emoji_btn)
        send_row.addWidget(self.sticker_btn)
        send_row.addWidget(self.input, 1)
        send_row.addWidget(self.tr_btn)
        send_row.addWidget(self.send_btn)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 6, 6, 8)
        rl.addLayout(head_row)
        rl.addWidget(self.reply_lbl)
        rl.addWidget(self.msg_search)
        rl.addWidget(self.stack, 1)
        rl.addLayout(send_row)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.addWidget(self.info_panel)   # третья колонка: профиль (как в TG Desktop)
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
        self.act_accounts = QAction(self)       # аккаунты: до 100 дополнительных
        self.act_accounts.triggered.connect(self.open_accounts)
        self.act_games = QAction(self)          # мини-игры: скоротать ожидание ответа
        self.act_games.setShortcut(QKeySequence("Ctrl+G"))
        self.act_games.triggered.connect(self.open_games)
        self.act_gsearch = QAction(self)       # глобальный поиск по всем чатам
        self.act_gsearch.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self.act_gsearch.triggered.connect(self.open_gsearch)
        self.act_media = QAction(self)         # медиа переписки по категориям
        self.act_media.setShortcut(QKeySequence("Ctrl+M"))
        self.act_media.triggered.connect(self.open_media_search)
        self.act_translate = QAction(self)    # перевод переписки вкл/выкл
        self.act_translate.triggered.connect(self.on_translate)
        self.act_quit = QAction(self)
        self.act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.act_quit.triggered.connect(lambda *_: self.close())
        for act in (self.act_info, self.act_search, self.act_call, self.act_call_tel,
                    self.act_settings, self.act_accounts, self.act_updates, self.act_games,
                    self.act_gsearch, self.act_media, self.act_translate):
            self.menu.addAction(act)
        self.menu.addSeparator()
        self.menu.addAction(self.act_quit)
        QShortcut(QKeySequence("Escape"), self, activated=self.close_search)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.open_emoji)
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self.open_stickers)

        self.retranslate()
        self.apply_cat_cursor()

        # статус «в сети» истекает сам, если Telegram не прислал «был(а) в сети»
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.tick_status)
        self.status_timer.start(20000)

    # --- служебное ---

    def retranslate(self):
        self.setWindowTitle(tr("title"))
        self.menu.setTitle(tr("menu"))
        self.act_settings.setText(tr("settings"))
        self.act_accounts.setText(tr("accounts"))
        self.act_search.setText(tr("search"))
        self.act_info.setText(tr("info"))
        self.act_call.setText(tr("call"))
        self.act_call_tel.setText(tr("call_tel"))
        self.act_updates.setText(tr("updates"))
        self.act_games.setText(tr("games"))
        self.act_gsearch.setText(tr("gsearch"))
        self.act_media.setText(tr("media_search"))
        self.act_translate.setText(tr("translate_chat"))
        self.info_btn.setToolTip(tr("profile"))
        self.info_media_btn.setText("🗂 " + tr("media_search"))
        self.game_btn.setToolTip(tr("play_app"))
        self.reply_lbl.setText(f"↩ {tr('replying')} · Esc")
        self.act_quit.setText(tr("quit"))
        self.chat_filter.setPlaceholderText(tr("find_chats"))
        self.msg_search.setPlaceholderText(tr("find_msgs"))
        self.input.setPlaceholderText(tr("write"))
        self.attach.setToolTip(tr("attach_video"))
        self.tr_btn.setToolTip(tr("tr_input"))
        self.send_btn.setToolTip("🐱 ➤")
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
        return task   # вызывающий может дождаться или проверить task.done()

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

    def apply_cat_cursor(self):
        """Курсор-кот с палочкой: палочка — указатель, кончик = точка клика.
        Поле ввода и просмотр чата оставляют обычный курсор: в тексте нужно
        точно попадать в буквы, а над ссылками кот всё равно сменяется рукой."""
        if S.get("cat_cursor", True):
            cur = QCursor(cat_cursor_pixmap(), 1, 1)
        else:
            cur = QCursor(Qt.CursorShape.ArrowCursor)
        self.setCursor(cur)
        self.chats.setCursor(cur)

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
            self.game_btn.hide()
            return
        ok = self.can_call(self.current)
        has_phone = ok and bool(self.phone_of(self.current))
        self.call_btn.setEnabled(ok)
        self.call_btn.setToolTip(tr("call" if ok else "call_people_only"))
        self.tel_btn.setEnabled(has_phone)
        self.tel_btn.setToolTip(tr("call_tel" if has_phone else "call_no_phone"))
        self.call_btn.show()
        self.tel_btn.show()
        ent = self.entities.get(self.current)
        # 🎮 показываем только в чатах с ботами (или пока неизвестно, кто это)
        self.game_btn.setVisible(ent is None or bool(getattr(ent, "bot", False)))
        title = self.titles.get(self.current, "?")
        status = self.status_text(self.current)
        if status:
            title += f"  ·  {status}"
        self.header.setText(title.replace("&", "&&"))
        self.header.setIcon(self.icon_for(self.current))
        self.header.show()

    def on_bot_app(self, *_):
        """🎮 в шапке чата с ботом: открыть его мини-приложение."""
        if self.current is not None:
            self.spawn(self.open_bot_app())

    async def open_bot_app(self):
        """«Играть»: главное мини-приложение бота (Hamster Kombat и другие).

        URL приложения берём из «кнопки меню» бота (main web app из полного
        профиля), платформу подставляем из настроек — поэтому мини-игры,
        не пускающие десктопных клиентов, открываются в режиме «Android».
        Запрос RequestWebView возвращает ссылку с подписанными данными
        приложения (tgWebAppData) — её открывает браузер."""
        did = self.current
        st = self.statusBar()
        if did is None:
            return
        try:
            ent = await self.client.get_entity(did)
            if not getattr(ent, "bot", False):
                st.showMessage(tr("not_bot"), 5000)
                return
            url = None
            try:   # у бота может быть «главное» приложение в кнопке меню
                full = await self.client(functions.users.GetFullUserRequest(ent))
                btn = getattr(full.full_user, "bot_info", None)
                btn = getattr(btn, "menu_button", None)
                url = getattr(btn, "url", None)
            except Exception:
                pass
            plat = S.get("device")
            plat = plat if plat in ("android", "ios") else "desktop"
            kw = dict(peer=did, bot=ent, platform=plat)
            if url:
                kw["url"] = url
            res = await self.client(functions.messages.RequestWebViewRequest(**kw))
            if getattr(res, "url", None):
                QDesktopServices.openUrl(QUrl(res.url))
        except Exception as e:
            st.showMessage(f"{tr('error')}: {e}", 6000)

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
        elif (m.gif is not None or m.video is not None) and m.document is not None:
            thumb = pick_thumb(m.document)                   # гифка или видео — кадр-превью
            if thumb is not None:
                return thumb, 360, (thumb.w, thumb.h)
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
        did = m.chat_id if m.chat_id is not None else self.current
        spec = self.image_spec(m) if S["show_photos"] else None
        if spec:
            thumb, maxw, (sw, sh) = spec
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
            if (m.video or (m.document is not None
                            and (m.document.mime_type or "").startswith("video/"))) \
                    and did is not None:
                tag = (f'<a href="catvid:{did}/{m.id}" style="color:{P["accent"]}">'
                       f'{tag} ▶</a>')   # клик — скачать и открыть системным плеером
            body = f"<i>{tag}</i> {body}".strip()
        trans = self.translations.get((did, m.id))
        if trans:   # автоперевод включён и перевод уже готов
            body += f'<br><i style="color:{P["dim"]}">🌐 {html.escape(trans)}</i>'
        btns = getattr(m, "buttons", None)   # инлайн-кнопки ботов — кликабельные
        if btns and did is not None:
            cells = []
            for ri, row in enumerate(btns):
                for ci, b in enumerate(row):
                    cells.append(f'<a href="catbtn:{did}/{m.id}/{ri}/{ci}" '
                                 f'style="color:{P["accent"]}">[{html.escape(b.text)}]</a>')
            body += "<br>" + " ".join(cells)
        if key:
            if m.photo:
                href, kind = f"catphoto:{did}/{m.id}", "photo"
            elif m.sticker and (m.file.mime_type or "") == "application/x-tgsticker":
                href, kind = None, "sticker"   # tgs вне Qt не проиграть — только кадр
            else:   # гифки, видео и webm-стикеры: клик — просмотр/проигрывание
                href, kind = f"catvid:{did}/{m.id}", "video"
            img = f'<img src="{key}"{dims}>'
            if href:
                img = f"<a href=\"{href}\">{img}</a>"
            body = f"{img}<br>{body}"
            if kind == "photo" and did is not None:
                self.chat_photos.setdefault(did, {})[m.id] = key   # листается в просмотрщике
        return (f'<p style="margin:6px 0"><b style="color:{color}">{html.escape(who)}</b> '
                f'<a href="msg:{did}/{m.id}" style="color:{P["dim"]}; '
                f'text-decoration:none">{when}</a><br>{body}</p>')

    def scroll_down(self):
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    async def show_message(self, m):
        if self.searching or m.id in self.shown:
            return
        self.shown.add(m.id)
        did = m.chat_id if m.chat_id is not None else self.current
        if m.message and did in self.translating and (did, m.id) not in self.translations:
            try:
                res = await asyncio.to_thread(translate_text, m.message, tg_lang())
                if res:
                    self.translations[(did, m.id)] = res
            except Exception:
                pass   # сети нет или endpoint недоступен — покажем как есть
        todo = []
        chunk = await self.render(m, todo=todo)
        if chunk:
            d = m.date.astimezone().date()
            if self.last_day is not None and d != self.last_day:
                self.view.append(self.day_sep(d))   # начался новый день
            self.last_day = d
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
        self.last_day = None
        self.cancel_reply()
        if self.info_panel.isVisible():   # третья колонка показывает профиль этого чата
            self.spawn(self.fill_info(did))
        self.msg_search.clear()
        self.msg_search.hide()
        self.unread[did] = 0
        self.refresh_item(did)
        self.view.clear()
        self.stack.setCurrentIndex(1)
        self.update_header()
        self.spawn(self.load_history(did))

    async def load_history(self, did, anchor=None):
        self.epoch += 1
        epoch = self.epoch
        self.paging = False
        self.chat_photos[did] = {}   # просмотрщик листает только фото открытого чата
        if anchor:   # прыжок к сообщению из поиска: оно окажется внизу окна
            msgs = await self.client.get_messages(did, limit=PAGE, offset_id=anchor)
        else:
            msgs = await self.client.get_messages(did, limit=PAGE)
        if did != self.current or self.searching or epoch != self.epoch:
            return   # уже переключились / идёт поиск / запущена более свежая загрузка
        parts, todo = [], []
        prev_day = None
        for m in reversed(msgs):
            self.shown.add(m.id)
            d = m.date.astimezone().date()
            if d != prev_day:   # группировка сообщений по дням, как в Telegram Desktop
                parts.append(self.day_sep(d))
                prev_day = d
            parts.append(await self.render(m, todo=todo))
        if did != self.current or self.searching or epoch != self.epoch:
            return
        self.last_day = prev_day
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

    def day_sep(self, d):
        """Разделитель дней в истории — группировка по дате, как в Telegram Desktop."""
        today = datetime.now().astimezone().date()
        txt = tr("day_today") if d == today else d.strftime("%d.%m.%Y")
        return (f'<p align="center" style="color:{pal()["dim"]}; margin:8px 0">'
                f'{html.escape(txt)}</p>')

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
                prev_day = self.last_day
                for m in reversed(msgs):
                    self.shown.add(m.id)
                    d = m.date.astimezone().date()
                    if d != prev_day:   # разделители дней и в подгруженной части
                        parts.append(self.day_sep(d))
                        prev_day = d
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

    def on_translate_input(self, *_):
        """🌐 у поля ввода: перевести набранное сообщение перед отправкой."""
        if self.input.text().strip():
            self.spawn(self.translate_input())

    async def translate_input(self):
        """Переводит текст из поля ввода на язык из настроек, подменяя его."""
        text = self.input.text().strip()
        if not text:
            return
        self.statusBar().showMessage(tr("translating"), 3000)
        try:
            res = await asyncio.to_thread(translate_text, text, tg_lang())
        except Exception as e:
            self.statusBar().showMessage(f"{tr('error')}: {e}", 6000)
            return
        if res:
            self.input.setText(res)
            self.statusBar().clearMessage()

    async def send(self, did, text):
        reply, self.reply_to = self.reply_to, None   # ответ уходит вместе с сообщением
        m = await self.client.send_message(did, text, reply_to=reply)
        self.cancel_reply()
        if did == self.current:
            await self.show_message(m)

    def on_attach(self, *_):
        if self.current is None:
            return
        flt = (f"{tr('video_files')} (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.3gp);;"
               f"{tr('all_files')} (*)")
        # DontUseNativeDialog: родной GTK-выбирщик падает без gsettings-схем
        # (GLib-GIO-ERROR: 'org.gtk.Settings.FileChooser' is not installed) —
        # берём собственный диалог Qt, он ни от каких схем не зависит
        path, _flt = QFileDialog.getOpenFileName(
            self, tr("pick_video"), str(Path.home()), flt,
            options=QFileDialog.Option.DontUseNativeDialog)
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
        for cls, key in ((SnakeGame, "snake"), (Game2048, "g2048"), (TetrisGame, "tetris"),
                         (MinesGame, "mines"), (MarioGame, "mario"), (KartGame, "kart"),
                         (ArkanoidGame, "arka"), (ChessGame, "chess"),
                         (CheckersGame, "checkers"), (TanksGame, "tanks"),
                         (CardsGame, "cards"), (Game15, "g15"),
                         (PairsGame, "pairs"), (XoGame, "xo")):
            tabs.addTab(GameScaleView(cls()), tr(key))
        hint = QLabel(tr("wait_hint"))
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay = QVBoxLayout(dlg)
        lay.addWidget(tabs)
        lay.addWidget(hint)
        dlg.showMaximized()   # игры растянутся на весь экран

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
        scroll.setMinimumHeight(420)   # тянется за окном, а не стоит колом
        lay = QVBoxLayout(dlg)
        lay.addWidget(scroll)
        dlg.resize(640, 640)   # окно эмодзи тоже растягивается мышью
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
            if self.isMinimized():   # чат открыт, но окно свёрнуто — тоже уведомим
                self.tray_notify(did, event.message)
        elif did in self.items and not event.message.out:
            self.unread[did] = self.unread.get(did, 0) + 1
            self.refresh_item(did)
            self.tray_notify(did, event.message)

    def tray_notify(self, did, m):
        """Уведомление в трее о новом сообщении (как всплывашки Telegram Desktop)."""
        if self.tray is None:   # система без трея — уведомлять некуда
            return
        if not S.get("notify", True):   # уведомления выключены в настройках
            return
        title = self.titles.get(did, "?")
        body = (m.message or media_tag(m) or "…").split("\n")[0][:100]
        try:
            if S.get("notify_sound", True):
                QApplication.beep()
            self.tray.showMessage(f"🐱 {title}", body,
                                  QSystemTrayIcon.MessageIcon.Information, 5000)
            self.last_notify = did
        except Exception:
            pass   # система без трея — молча пропускаем

    def on_notify_click(self, *_):
        if self.last_notify is not None:
            self.open_peer(self.last_notify)
            self.last_notify = None

    # --- поиск по сообщениям ---

    def open_search(self, *_):
        if self.current is None:
            return
        self.msg_search.show()
        self.msg_search.setFocus()
        self.msg_search.selectAll()

    def close_search(self, *_):
        if self.reply_to is not None:   # Esc сперва отменяет ответ, потом поиск
            self.cancel_reply()
            return
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

    # --- ссылки в сообщениях: браузер и просмотр видео ---

    def on_anchor(self, url):
        """Клик по ссылке в переписке: http(s) — браузер, catvid: — видео,
        catphoto: — полноэкранный просмотр, msg: — меню сообщения."""
        s = url.toString()
        if s.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(s))
            return
        if s.startswith("catvid:"):
            try:
                did, mid = s[len("catvid:"):].split("/")
                self.spawn(self.play_video(int(did), int(mid)))
            except (ValueError, TypeError):
                pass
            return
        if s.startswith("catphoto:"):
            try:
                did, mid = s[len("catphoto:"):].split("/")
                self.open_photo(int(did), int(mid))
            except (ValueError, TypeError):
                pass
            return
        if s.startswith("catbtn:"):
            try:
                did, mid, r, c = s[len("catbtn:"):].split("/")
                self.spawn(self.bot_button(int(did), int(mid), int(r), int(c)))
            except ValueError:
                pass
            return
        if s.startswith("msg:"):
            self.msg_ctx(s[len("msg:"):])

    async def bot_button(self, did, mid, r, c):
        """Клик по инлайн-кнопке бота. Веб-приложения (Hamster Kombat и другие
        мини-игры) запускаем запросом RequestWebView: сервер сам вшивает в
        выданную ссылку подписанные данные приложения (tgWebAppData), а
        платформу подставляем из настроек — поэтому мини-игры, не пускающие
        десктопных клиентов, работают в режиме «Android»/«iPhone».
        Кнопки-ссылки открываем в браузере, кнопки-«отзывы» (callback)
        прожимаем и показываем ответ бота."""
        try:
            m = await self.client.get_messages(did, ids=mid)
            btn = m.buttons[r][c]
        except Exception:
            return
        try:
            kind = type(btn).__name__
            if kind == "KeyboardButtonWebView":   # мини-приложение
                plat = S.get("device")
                plat = plat if plat in ("android", "ios") else "desktop"
                res = await self.client(functions.messages.RequestWebViewRequest(
                    peer=did, bot=m.sender_id, platform=plat, url=btn.url))
                if getattr(res, "url", None):
                    QDesktopServices.openUrl(QUrl(res.url))
                return
            if kind == "KeyboardButtonCallback":   # кнопка с ответом бота
                res = await self.client(functions.messages.GetBotCallbackAnswerRequest(
                    peer=did, msg_id=mid, data=btn.data))
                if getattr(res, "message", None):
                    QMessageBox.information(self, tr("title"), res.message)
                return
            url = getattr(btn, "url", None)   # обычная ссылка
            if url:
                QDesktopServices.openUrl(QUrl(url))
        except Exception as e:
            self.statusBar().showMessage(f"{tr('error')}: {e}", 6000)

    async def play_video(self, did, mid):
        """Видео: со стримом плеер открывается, не дожидаясь конца скачивания
        (остаток догружается в фоне), без стрима — полная загрузка, потом просмотр."""
        st = self.statusBar()
        try:
            m = await self.client.get_messages(did, ids=mid)
            if m is None or m.media is None:
                st.showMessage(f"{tr('error')}: {tr('m_video')}", 6000)
                return
            name = m.file.name or "video.mp4"
            suffix = Path(name).suffix or ".mp4"
            path = CACHE_DIR / f"catgram-video-{mid}{suffix}"

            def progress(sent, total):
                pct = int(sent * 100 / total) if total else 0
                st.showMessage(f"⬇ {name} — {pct}%")

            if S.get("stream_video", True):
                await self.stream_video(m, path, name, progress)
            else:   # старое поведение: скачать целиком, потом открыть
                st.showMessage(f"⬇ {name}…")
                await m.download_media(file=str(path), progress_callback=progress)
                st.clearMessage()

            def sys_play():   # запасной вариант — системный плеер
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

            if MULTIMEDIA:
                VideoViewer(self, path, sys_play)
            else:
                sys_play()
        except Exception as e:
            st.showMessage(f"{tr('error')}: {e}", 8000)

    async def stream_video(self, m, path, name, progress):
        """Стрим: скачивание идёт параллельно, плеер стартует, как только
        набрался первый буфер. Телеграмовские mp4 обычно пригодны для этого
        (metainfo в начале файла); если конкретное видео «не стримится»,
        перемотка может подвисать до конца загрузки — тогда выключите стрим
        в настройках и скачайте целиком."""
        st = self.statusBar()
        total = m.file.size if m.file else 0
        # буфер: 25% файла, но не меньше 512 КБ и не больше 4 МБ
        buf = min(4 * 1024 * 1024, max(512 * 1024, total // 4)) \
            if total else 2 * 1024 * 1024

        async def dl():   # качаем в фоне, прогресс — в статусной строке
            await m.download_media(file=str(path), progress_callback=progress)
            st.clearMessage()

        task = self.spawn(dl())
        waited = 0.0
        while waited < 30:   # 30 секунд хватит любому буферу; обрыв сети не зациклит
            await asyncio.sleep(0.2)
            waited += 0.2
            try:
                if path.stat().st_size >= buf:
                    break   # буфер готов — можно начинать показ
            except OSError:
                pass
            if task.done():   # скачалось быстрее, чем мы ждали буфер
                break

    # --- контекстное меню сообщения (как правый клик в Telegram Desktop) ---

    def msg_ctx(self, ref):
        """ref «чат/сообщение» из якоря msg:... — показать меню действия.

        menu.exec() внутри корутины — верный способ подвесить asyncio: цикл
        крутится в Qt, а задача msg_menu в это время «выполняется», и другие
        задачи получить RuntimeError «Cannot enter into task». Поэтому сначала
        доносим сообщение задачей, а меню показываем из Qt-таймера, когда
        задача уже завершилась."""
        try:
            did, mid = ref.split("/")
            did, mid = int(did), int(mid)
        except (ValueError, TypeError):
            return

        def show_menu(m):
            menu = QMenu(self)
            if m.message:
                menu.addAction("📋 " + tr("ctx_copy"), lambda: self.copy_text(m.message))
            menu.addAction("↩ " + tr("ctx_reply"), lambda: self.start_reply(did, mid))
            menu.addAction("➡ " + tr("ctx_fwd"), lambda: self.spawn(self.fwd_pick(did, mid)))
            menu.addAction("📌 " + tr("ctx_pin"), lambda: self.spawn(self.pin_msg(did, mid)))
            menu.addAction("🗑 " + tr("ctx_del"), lambda: self.spawn(self.del_msg(did, mid)))
            menu.exec(QCursor.pos())

        async def fetch():
            try:
                m = await self.client.get_messages(did, ids=mid)
            except Exception:
                return
            if m is not None:
                QTimer.singleShot(0, lambda: show_menu(m))

        self.spawn(fetch())

    def copy_text(self, text):
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("📋", 2000)

    def start_reply(self, did, mid):
        """Ответ на сообщение: строка-подсказка над полем ввода, Esc — отмена."""
        if did != self.current:
            return
        self.reply_to = mid
        self.reply_lbl.setText(f"↩ {tr('replying')} · Esc")
        self.reply_lbl.show()
        self.input.setFocus()

    def cancel_reply(self):
        self.reply_to = None
        self.reply_lbl.hide()

    async def fwd_pick(self, did, mid):
        """Пересылка сообщения: выбираем чат из списка слева (не модально)."""
        names, dids = [], []
        for row in range(self.chats.count()):
            it = self.chats.item(row)
            did2 = it.data(Qt.ItemDataRole.UserRole)
            if did2 is None or did2 == did:
                continue
            dids.append(did2)
            names.append(self.titles.get(did2, "?"))
        if not dids:
            return
        fut = asyncio.get_running_loop().create_future()
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("fwd_pick"))
        dlg.setModal(False)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        combo = QComboBox()
        combo.addItems(names)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                               QDialogButtonBox.StandardButton.Cancel)
        lay = QVBoxLayout(dlg)
        lay.addWidget(combo)
        lay.addWidget(box)

        def accept(*_):
            if not fut.done():
                fut.set_result(combo.currentIndex())
            dlg.close()

        def cancel(*_):
            if not fut.done():
                fut.cancel()
            dlg.close()

        box.accepted.connect(accept)
        box.rejected.connect(cancel)
        dlg.destroyed.connect(lambda *_: fut.cancel() if not fut.done() else None)
        dlg.show()
        try:
            sel = await fut
        except asyncio.CancelledError:
            return
        if sel is None or not 0 <= sel < len(dids):
            return
        try:
            await self.client.forward_messages(dids[sel], mid, did)
            self.statusBar().showMessage(tr("fwd_ok"), 4000)
        except Exception as e:
            self.statusBar().showMessage(f"{tr('error')}: {e}", 8000)

    async def pin_msg(self, did, mid):
        try:
            await self.client.pin_message(did, mid)
            self.statusBar().showMessage("📌 " + tr("pin_ok"), 4000)
        except Exception as e:
            self.statusBar().showMessage(f"{tr('error')}: {e}", 8000)

    async def del_msg(self, did, mid):
        try:
            await self.client.delete_messages(did, [mid], revoke=True)
            self.statusBar().showMessage(tr("del_ok"), 4000)
            if did == self.current:
                self.shown.clear()
                await self.load_history(did)
        except Exception as e:
            self.statusBar().showMessage(f"{tr('error')}: {e}", 8000)

    # --- полноэкранный просмотр фото (Media::View в Telegram Desktop) ---

    def open_photo(self, did, mid):
        """Открывает фото в просмотрщике; стрелки листают все фото этого чата."""
        photos = sorted(self.chat_photos.get(did, {}).items())
        if not photos:
            return
        items = [(m2, self.photo_cache.get(k)) for m2, k in photos]
        index = next((i for i, (m2, _im) in enumerate(items) if m2 == mid), 0)
        PhotoViewer(self, items, index)

    # --- третья колонка: панель профиля (как в Telegram Desktop) ---

    def toggle_info(self, *_):
        """Показать/спрятать панель профиля собеседника справа."""
        if self.current is None:
            return
        self.info_panel.setVisible(not self.info_panel.isVisible())
        if self.info_panel.isVisible():
            self.spawn(self.fill_info(self.current))

    async def fill_info(self, did):
        """Профиль: аватар, имя, @юзернейм, телефон, о себе, число участников."""
        ent = self.entities.get(did)
        if ent is None:
            return
        icon = self.real_icons.get(did) or self.cat_icons.get(did)
        if icon is not None:
            self.info_avatar.setPixmap(icon.pixmap(96, 96))
        self.info_title.setText(self.titles.get(did) or get_display_name(ent) or "?")
        user = getattr(ent, "username", None)
        self.info_user.setText(f"@{user}" if user else "")
        phone = getattr(ent, "phone", None)
        self.info_phone.setText(f"+{phone}" if phone else "")
        about, members = "", None
        try:
            if isinstance(ent, types.User):
                full = await self.client(functions.users.GetFullUserRequest(ent))
                about = full.full_user.about or ""
            elif isinstance(ent, types.Channel):
                full = await self.client(functions.channels.GetFullChannelRequest(ent))
                about = full.full_chat.about or ""
                members = getattr(full.full_chat, "participants_count", None)
            else:
                full = await self.client(functions.messages.GetFullChatRequest(did))
                about = full.full_chat.about or ""
        except Exception:
            pass   # нет доступа к полному профилю — покажем то, что есть
        self.info_about.setText(about)
        self.info_members.setText(f"{members} 👥" if members else "")

    # --- автоперевод переписки ---

    def on_translate(self, *_):
        """Вкл/выкл автоперевод открытого чата на язык интерфейса."""
        if self.current is None:
            return
        did = self.current
        if did in self.translating:
            self.translating.discard(did)
            for k in [k for k in self.translations if k[0] == did]:
                self.translations.pop(k, None)
            if not self.searching:
                self.shown.clear()
                self.spawn(self.load_history(did))
            return
        self.translating.add(did)
        self.statusBar().showMessage(tr("translating"), 6000)
        self.spawn(self.translate_history(did))

    async def translate_history(self, did):
        """Переводит последнюю страницу сообщений и перезагружает окно чата."""
        msgs = await self.client.get_messages(did, limit=PAGE)
        sem = asyncio.Semaphore(4)   # не заваливаем переводчик параллельными запросами

        async def one(m):
            if not m.message or (did, m.id) in self.translations:
                return
            async with sem:
                try:
                    res = await asyncio.to_thread(translate_text, m.message, tg_lang())
                except Exception:
                    return
            if res:
                self.translations[(did, m.id)] = res

        await asyncio.gather(*(one(m) for m in msgs))
        if did in self.translating and did == self.current and not self.searching:
            self.shown.clear()
            await self.load_history(did)

    # --- глобальный поиск по всем чатам ---

    def open_gsearch(self, *_):
        """Поиск сразу по всем чатам: диалоги, контакты и сообщения."""
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("gsearch"))
        dlg.setModal(False)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.resize(640, 480)
        edit = QLineEdit()
        edit.setPlaceholderText(tr("gs_hint"))
        lst = QListWidget()

        def on_pick(item):
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                self.open_peer(*data)
        lst.itemDoubleClicked.connect(on_pick)
        lay = QVBoxLayout(dlg)
        lay.addWidget(edit)
        lay.addWidget(lst, 1)

        def on_return(*_):
            q = edit.text().strip()
            if q:
                lst.clear()
                self.spawn(self.gsearch_run(q, lst))
        edit.returnPressed.connect(on_return)
        edit.setFocus()
        dlg.show()

    async def gsearch_run(self, q, lst):
        """Собирает результаты: сначала чаты и контакты, потом сообщения."""
        found = 0

        def head(txt):
            it = QListWidgetItem(f"— {txt} —")
            it.setData(Qt.ItemDataRole.UserRole, None)
            lst.addItem(it)

        try:
            res = await self.client(functions.contacts.SearchRequest(q=q, limit=20))
        except Exception:
            res = None
        if res is not None:
            head(f"💬 {tr('gs_chats')}")
        for peer in list(getattr(res, "my_results", None) or []) \
                + list(getattr(res, "results", None) or []):
            try:
                ent = await self.client.get_entity(peer)
                title = get_display_name(ent) or "?"
            except Exception:
                continue
            it = QListWidgetItem(f"💬 {title}")
            it.setData(Qt.ItemDataRole.UserRole, (ent.id, ent, title, None))
            lst.addItem(it)
            found += 1
        try:
            g = await self.client(functions.messages.SearchGlobalRequest(
                q=q, offset_rate=0, offset_id=0, offset_peer=types.InputPeerEmpty(),
                limit=30))
        except Exception:
            g = None
        if g is not None and getattr(g, "messages", None):
            head(f"✉ {tr('gs_msgs')}")
        for m in list(getattr(g, "messages", None) or []):
            pid = getattr(m, "peer_id", None)
            did = getattr(pid, "user_id", None) or getattr(pid, "chat_id", None) \
                or getattr(pid, "channel_id", None)
            if did is None or not getattr(m, "message", None):
                continue
            title = "?"
            for c in list(getattr(g, "chats", None) or []) \
                    + list(getattr(g, "users", None) or []):
                if c.id == did:
                    title = get_display_name(c) or "?"
                    break
            when = m.date.astimezone().strftime("%d.%m.%y %H:%M")
            it = QListWidgetItem(f"✉ {title}: {m.message.splitlines()[0][:70]}  ({when})")
            it.setData(Qt.ItemDataRole.UserRole, (did, None, title, m.id))
            lst.addItem(it)
            found += 1
        if not found:
            lst.addItem(f"— {tr('nothing')} —")

    def open_peer(self, did, ent=None, title=None, mid=None):
        """Открывает чат по id: выбирает строку в списке или создаёт её сверху."""
        if did is None:
            return
        if title and did not in self.titles:
            self.titles[did] = title
        if ent is not None:
            self.entities[did] = ent
        if did != self.current:
            if did in self.items:
                self.chats.setCurrentItem(self.items[did])
            else:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, did)
                item.setIcon(self.icon_for(did))
                self.items[did] = item
                self.chats.insertItem(0, item)
                self.refresh_item(did)
                self.chats.setCurrentItem(item)
        if mid is not None:
            self.spawn(self.load_history(did, anchor=mid + 1))   # прыжок к сообщению

    # --- медиа переписки по категориям ---

    def open_media_search(self, *_):
        """Категории переписки: фото, видео, ссылки, музыка, контакты."""
        if self.current is None:
            return
        did = self.current
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("media_search"))
        dlg.setModal(False)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.resize(640, 460)
        tabs = QTabWidget()
        cats = ((tr("cat_photos"), types.InputMessagesFilterPhotos()),
                (tr("cat_videos"), types.InputMessagesFilterVideo()),
                (tr("cat_links"), types.InputMessagesFilterUrl()),
                (tr("cat_music"), types.InputMessagesFilterMusic()))
        if getattr(types, "InputMessagesFilterContacts", None) is not None:
            cats += ((tr("cat_contacts"), types.InputMessagesFilterContacts()),)
        for label, flt in cats:
            lw = QListWidget()
            lw.itemDoubleClicked.connect(
                lambda it: self.open_peer(*it.data(Qt.ItemDataRole.UserRole)))
            tabs.addTab(lw, label)
            self.spawn(self.fill_media_tab(did, flt, lw))
        lay = QVBoxLayout(dlg)
        lay.addWidget(tabs)
        dlg.show()

    async def fill_media_tab(self, did, flt, lw):
        """Наполняет вкладку медиа-поиска; двойной клик прыгает к сообщению."""
        try:
            async for m in self.client.iter_messages(did, filter=flt, limit=50):
                if m.message:
                    txt = m.message.splitlines()[0][:80]
                elif m.file is not None and m.file.name:
                    txt = m.file.name
                else:
                    txt = media_tag(m) or "?"
                when = m.date.astimezone().strftime("%d.%m.%y %H:%M")
                it = QListWidgetItem(f"{when}   {txt}")
                it.setData(Qt.ItemDataRole.UserRole, (did, None, None, m.id))
                lw.addItem(it)
        except Exception as e:
            lw.addItem(f"{tr('error')}: {e}")

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

    def open_accounts(self, *_):
        """Аккаунты: добавить (до 100 дополнительных), переключиться или удалить.

        Переключение перезапускает catgram с другой сессией — так каждый аккаунт
        живёт в своём окне со своей историей, и ничего не путается.
        """
        names = account_names()
        cur = str(S.get("account") or APP)   # после старых версий ключа может не быть
        if cur not in names:
            names.insert(0, cur)
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("accounts"))
        dlg.setMinimumWidth(420)
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        for n in names:
            mark = "   ✓" if n == cur else ""
            item = QListWidgetItem(account_label(n) + mark)
            item.setData(Qt.ItemDataRole.UserRole, n)
            lst.addItem(item)
        if cur in names:
            lst.setCurrentRow(names.index(cur))
        lay.addWidget(lst, 1)
        row = QHBoxLayout()
        add = QPushButton("➕ " + tr("acc_add"))
        switch = QPushButton(tr("acc_switch"))
        remove = QPushButton(tr("acc_remove"))
        row.addWidget(add)
        row.addWidget(switch)
        row.addWidget(remove)
        lay.addLayout(row)

        def chosen():
            item = lst.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item else None

        def on_add():
            slot = free_account_slot()
            if slot is None:
                self.statusBar().showMessage(tr("acc_limit"), 6000)
                return
            if QMessageBox.question(dlg, tr("accounts"),
                                    tr("acc_switch_q").format(name=slot)) \
                    == QMessageBox.StandardButton.Yes:
                dlg.accept()
                self.switch_account(slot)

        def on_switch():
            name = chosen()
            if not name or name == cur:
                return
            if QMessageBox.question(dlg, tr("accounts"),
                                    tr("acc_switch_q").format(name=account_label(name))) \
                    == QMessageBox.StandardButton.Yes:
                dlg.accept()
                self.switch_account(name)

        def on_remove():
            name = chosen()
            if not name or name == cur:   # текущий удалить нельзя
                return
            if QMessageBox.question(dlg, tr("accounts"),
                                    tr("acc_del_q").format(name=account_label(name))) \
                    != QMessageBox.StandardButton.Yes:
                return
            for suffix in (".session", ".session-journal"):
                try:
                    (DATA_DIR / f"{name}{suffix}").unlink()
                except OSError:
                    pass
            S.setdefault("account_labels", {}).pop(name, None)
            save_settings()
            lst.takeItem(lst.currentRow())

        add.clicked.connect(on_add)
        switch.clicked.connect(on_switch)
        remove.clicked.connect(on_remove)
        dlg.exec()

    def switch_account(self, name):
        """Сохраняет выбор и перезапускает catgram уже с другой сессией."""
        S["account"] = name
        save_settings()
        RESTART["want"] = True
        self.close()

    def open_settings(self, *_):
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("set_title"))
        dlg.setMinimumWidth(560)   # окно настроек можно растянуть шире
        form = QFormLayout(dlg)

        lang = QComboBox()
        for code, name in LANGS.items():
            lang.addItem(name, code)
        lang.setCurrentIndex(lang.findData(S["lang"]))
        trlang = QComboBox()   # на какой язык переводить переписку и набранное
        for code, name in LANGS.items():
            trlang.addItem(name, code)
        trlang.setCurrentIndex(trlang.findData(S.get("tr_lang") or S["lang"]))
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
        device = QComboBox()   # каким клиентом нас видит Telegram (мини-приложения)
        device.addItem(tr("dev_desktop"), "desktop")
        device.addItem(tr("dev_android"), "android")
        device.addItem(tr("dev_ios"), "ios")
        device.setCurrentIndex(device.findData(S.get("device", "desktop")))
        wallpaper = QComboBox()   # обои чата: бесшовный тайл, QSS растянет сам
        for key, val in (("wp_none", "none"), ("wp_paws", "paws"), ("wp_stars", "stars"),
                         ("wp_fish", "fish"), ("wp_hearts", "hearts"),
                         ("wp_file", "file")):
            wallpaper.addItem(tr(key), val)
        wallpaper.setCurrentIndex(wallpaper.findData(S["wallpaper"]))
        wall_file = [str(S.get("wallpaper_file") or "")]   # свои обои: путь к картинке

        def on_wall_pick(*_):   # выбираем картинку на этом компьютере
            # свой диалог Qt, а не GTK — без gsettings-схем нативный падает
            p, _f = QFileDialog.getOpenFileName(
                dlg, tr("set_wall_pick"), str(Path.home()),
                "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)",
                options=QFileDialog.Option.DontUseNativeDialog)
            if p:
                wall_file[0] = p
                wallpaper.setCurrentIndex(wallpaper.findData("file"))

        wall_pick = QPushButton(tr("set_wall_pick"))
        wall_pick.clicked.connect(on_wall_pick)
        photos = QCheckBox()
        photos.setChecked(S["show_photos"])
        notify = QCheckBox()   # как раздел «Уведомления» в Telegram Desktop
        notify.setChecked(S.get("notify", True))
        nsound = QCheckBox()
        nsound.setChecked(S.get("notify_sound", True))
        stream = QCheckBox()   # видео: плеер стартует до конца скачивания
        stream.setChecked(S.get("stream_video", True))
        catcur = QCheckBox()   # курсор-кот с палочкой (можно выключить)
        catcur.setChecked(S.get("cat_cursor", True))
        noise = QCheckBox()
        noise.setChecked(S["noise_suppression"])
        noise_test = QPushButton(tr("test_noise"))

        def on_test_noise(*_):   # проверка без звонка: поднять, показать, убрать
            self.spawn(self.test_noise())
        noise_test.clicked.connect(on_test_noise)
        upd = QCheckBox()
        upd.setChecked(S["check_updates"])
        url = QLineEdit(S["update_url"])
        url.setPlaceholderText("https://api.github.com/repos/<user>/catgram/releases/latest")
        url.setMinimumWidth(360)

        form.addRow(tr("set_lang"), lang)
        form.addRow(tr("set_trlang"), trlang)
        form.addRow(tr("set_device"), device)
        form.addRow("", QLabel(f'<i style="color:{pal()["dim"]}">{tr("dev_note")}</i>'))
        form.addRow(tr("set_theme"), theme)
        form.addRow(tr("set_font"), size)
        form.addRow(tr("set_avatars"), avatars)
        wall_row = QWidget()
        wall_row_l = QHBoxLayout(wall_row)
        wall_row_l.setContentsMargins(0, 0, 0, 0)
        wall_row_l.addWidget(wallpaper)
        wall_row_l.addWidget(wall_pick)
        wall_row_l.addStretch(1)
        form.addRow(tr("set_wallpaper"), wall_row)
        form.addRow(tr("set_photos"), photos)
        form.addRow(tr("set_notify"), notify)
        form.addRow(tr("set_nsound"), nsound)
        form.addRow(tr("set_stream"), stream)
        form.addRow(tr("set_catcursor"), catcur)
        noise_row = QWidget()
        noise_row_l = QHBoxLayout(noise_row)
        noise_row_l.setContentsMargins(0, 0, 0, 0)
        noise_row_l.addWidget(noise)
        noise_row_l.addWidget(noise_test)
        noise_row_l.addStretch(1)
        form.addRow(tr("set_noise"), noise_row)
        form.addRow(tr("set_upd_start"), upd)
        form.addRow(tr("set_upd_url"), url)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                               QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)

        if not dlg.exec():
            return
        S.update(lang=lang.currentData(), tr_lang=trlang.currentData(), theme=theme.currentData(),
                 font_size=size.value(), avatar_mode=avatars.currentData(),
                 device=device.currentData(),
                 wallpaper=wallpaper.currentData(), wallpaper_file=wall_file[0],
                 show_photos=photos.isChecked(), notify=notify.isChecked(),
                 notify_sound=nsound.isChecked(), stream_video=stream.isChecked(),
                 cat_cursor=catcur.isChecked(),
                 noise_suppression=noise.isChecked(),
                 check_updates=upd.isChecked(), update_url=url.text().strip())
        save_settings()
        self.apply_settings()

    def apply_settings(self):
        QApplication.instance().setStyleSheet(make_style())
        self.retranslate()
        self.apply_cat_cursor()
        if S["avatar_mode"] == "real":
            self.spawn(self.load_avatars())
        self.apply_icons()
        if self.current is not None and not self.searching:
            self.shown.clear()
            self.spawn(self.load_history(self.current))

    async def test_noise(self):
        """Проверка шумоподавления без звонка: поднять, показать способ, убрать."""
        st = await asyncio.to_thread(enable_noise_suppression)
        if st["method"]:
            await asyncio.to_thread(disable_noise_suppression, st)
            msg = tr("noise_on").format(name=NOISE_NAMES[st["method"]])
            if st.get("err"):   # работает, но RNNoise не поднялся — покажем почему
                msg += f"\n\n{st['err']}"
            QMessageBox.information(self, tr("set_noise"), msg)
        else:
            QMessageBox.warning(self, tr("set_noise"),
                                f'{tr("noise_off")}: {st["err"]}')

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

def device_params():
    """Каким клиентом нас видят серверы Telegram (список «Устройства» в настройках
    аккаунта). «Мобильный» режим нужен мини-приложениям вроде Hamster Kombat:
    платформа, переданная при запуске веб-приложения, берётся из этих полей,
    а многие мини-игры просто не открываются клиентам с платформой desktop.
    Telethon подставляет устройство при подключении — смена применяется перезапуском."""
    d = S.get("device", "desktop")
    if d == "android":   # типичный клиент Android, как у Telegram из Google Play
        return dict(device_model="Samsung SM-S928B", system_version="SDK 34",
                    app_version="11.6.2 (4444)")
    if d == "ios":
        return dict(device_model="iPhone 15 Pro", system_version="iOS 17.5.1",
                    app_version="11.6.2")
    return {}   # десктоп: пусть Telethon честно покажет машину пользователя


async def amain(closing):
    creds = await get_credentials()
    if not creds:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    account = str(S.get("account") or APP)   # какой аккаунт открывать
    client = TelegramClient(str(DATA_DIR / account), *creds, **device_params())
    try:
        title = tr("login") if account == APP else f'{tr("login")} — {account}'
        if not await login(client, title):
            return
        # файл сессии = доступ к аккаунту, держим его приватным
        for f in DATA_DIR.glob(f"{account}.session*"):
            f.chmod(0o600)
        try:   # запоминаем, чей это аккаунт — для списка «Аккаунты…»
            me = await client.get_me()
            S.setdefault("account_labels", {})[account] = get_display_name(me) or account
            save_settings()
        except Exception:
            pass
        win = CatGram(client, closing)
        win.showMaximized()   # сразу на весь экран; размер из resize() — запасной
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

    def on_sigint(*_):
        # Ctrl+C в терминале — выходим аккуратно, как при закрытии окна.
        # Без этого Python бросает KeyboardInterrupt прямо в Qt-колбэке
        # (таймер tick_status), и PyQt убивает процесс через qFatal:
        # SIGABRT и «образ памяти сброшен на диск», как было на v0.9.4.
        loop.call_soon_threadsafe(closing.set)

    signal.signal(signal.SIGINT, on_sigint)
    with loop:
        try:
            loop.run_until_complete(amain(closing))
        except KeyboardInterrupt:   # страховка, если сигнал придёт до handler'а
            pass
    if RESTART["want"]:   # переключение аккаунта: поднимаем себя заново
        os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == "__main__":
    main()
