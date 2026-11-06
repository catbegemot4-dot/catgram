<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!-- Created with Inkscape (http://www.inkscape.org/) -->

<svg
   version="1.1"
   id="svg1"
   width="554"
   height="554"
   viewBox="0 0 554 554"
   sodipodi:docname="images.png"
   inkscape:version="1.4.4 (dcaf3e7d9e, 2026-05-05)"
   xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
   xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
   xmlns="http://www.w3.org/2000/svg"
   xmlns:svg="http://www.w3.org/2000/svg">
  <defs
     id="defs1" />
  <sodipodi:namedview
     id="namedview1"
     pagecolor="#ffffff"
     bordercolor="#000000"
     borderopacity="0.25"
     inkscape:showpageshadow="2"
     inkscape:pageopacity="0.0"
     inkscape:pagecheckerboard="0"
     inkscape:deskcolor="#d1d1d1"
     showgrid="false"
     inkscape:zoom="0.933213"
     inkscape:cx="277"
     inkscape:cy="282.35783"
     inkscape:window-width="1440"
     inkscape:window-height="744"
     inkscape:window-x="0"
     inkscape:window-y="0"
     inkscape:window-maximized="1"
     inkscape:current-layer="g1" />
  <g
     inkscape:groupmode="layer"
     inkscape:label="Image"
     id="g1">
    <path
       style="fill:#000000"
       d="M 115.72921,100.72727 C 296.82398,324.68472 79.295938,280.75048 79.295938,280.75048 l 218.599612,45.00581 v 0"
       id="path1" />
    <path
       style="fill:#000000"
       d="m 230.38685,246.46035 c 99.6557,-109.29981 136.08897,-297.895553 99.6557,-109.29981 -36.43327,188.59575 -36.43327,188.59575 -36.43327,188.59575 l 10.71567,-87.86848 106.08511,291.46616 z"
       id="path2" />
  </g>
</svg>
![images](https://github.com/user-attachments/assets/3d2f933b-057a-4230-81fc-9518f0c0981a)
# кто хочет пусть предлогает идеи писать мне на @kotikst:matrix.org или на catbegemot4@gmail.com
# ничего комерческого,чисто хобби
<img width="1346" height="920" alt="Снимок экрана от 2026-11-03 15-28-00" src="https://github.com/user-attachments/assets/80135e2f-acff-4fd2-88e9-7a0540745289" />

# 🐱 catgram

Маленький клиент Telegram для Linux на **PyQt6 + Telethon**. Один файл, без лишнего:
котики вместо аватарок, тёмная и светлая темы, русский / English / українська.

*A tiny Telegram client for Linux (PyQt6 + Telethon). One file, cats for avatars. Short English notes are at the bottom.*

> Это неофициальный клиент. Он не связан с Telegram и работает через ваш личный аккаунт и ваши собственные ключи API.

## Что умеет
- есть звонки
- список чатов (первые 100) с поиском и счётчиками непрочитанных;
- **вся история переписки**: сначала последние 50 сообщений, дальше при прокрутке вверх подгружается по 100, пока не дойдёте до начала;
- фото и **стикеры** картинками (у анимированных стикеров виден один кадр); картинки качаются в фоне, текст появляется сразу;
- статус **«котится» / «не котится»** (то есть в сети или нет) в шапке чата, а в списке чатов помечены те, кто котится прямо сейчас;
- поиск по сообщениям в чате, информация о чате или человеке (клик по шапке);
- настройки: язык, тема, размер шрифта, режим аватарок (настоящие / только котики / без), проверка обновлений;
- отправка текстовых сообщений и **видео**: кнопка 📎 слева от поля ввода, прогресс в строке состояния, текст из поля ввода становится подписью к видео.

Чего нет: отправки фото и файлов (кроме видео), воспроизведения голосовых и видео, анимированных стикеров, звонков, секретных чатов.
Остальные вложения показываются меткой вроде `[файл]`.

## Установка

Нужен Python 3.9+.

```bash
git clone https://github.com/catbegemot4-dot/catgram.git
cd catgram
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 catgram.py
```

### ffmpeg (необязательно)

Для отправки видео желателен `ffmpeg` (вместе с ним ставится `ffprobe`): с ним catgram передаёт Telegram правильные размеры и длительность и прикладывает кадр-превью. Без него видео тоже уходит, но в чате получателя будет без превью. Лучше всего Telegram играет `.mp4`: файлы других форматов (`.mkv`, `.avi`) могут прийти как обычные файлы, перекодирования catgram не делает.

```bash
sudo apt install ffmpeg   # Debian/Ubuntu
```

### Ключи API

У каждого пользователя должны быть **свои** `api_id` и `api_hash`: получить их можно на
[my.telegram.org](https://my.telegram.org) в разделе *API development tools*. Дальше любой из способов:

1. вписать их в константы `API_ID` и `API_HASH` в начале `catgram.py` (не коммитьте их в публичный репозиторий!);
2. задать переменные окружения `CATGRAM_API_ID` и `CATGRAM_API_HASH`;
3. ничего не делать: при первом запуске catgram спросит их сам и сохранит в `~/.config/catgram/config.json` (права `0600`).

Потом он спросит номер телефона, код из Telegram и, если включена, пароль двухфакторной защиты.

## Горячие клавиши

| Клавиши  | Действие                |
|----------|-------------------------|
| `Ctrl+F` | поиск в чате (`Esc` закрывает) |
| `Ctrl+I` | информация о чате       |
| `Ctrl+,` | настройки               |
| `Ctrl+Q` | выход                   |

## Где что лежит

Каталоги учитывают `XDG_*_HOME`:

| Путь                     | Что там                                   |
|--------------------------|-------------------------------------------|
| `~/.config/catgram/`     | `config.json` (ключи API), `settings.json` |
| `~/.local/share/catgram/`| файл сессии Telegram                      |
| `~/.cache/catgram/`      | кэш аватарок                              |

⚠️ **Файл сессии даёт полный доступ к аккаунту.** Никому его не отправляйте и не коммитьте.
catgram сам выставляет на него права `0600`, а `.gitignore` в этом репозитории исключает `*.session*`.

## Обновления

В настройках можно указать адрес проверки обновлений, например
`https://api.github.com/repos/<user>/catgram/releases/latest`.
catgram сравнит `tag_name` последнего релиза со своей версией (константа `VERSION` в `catgram.py`),
так что **тег релиза должен совпадать с `VERSION`** (`v0.3.0` ↔ `0.3.0`).

## English

catgram is a minimal Telegram desktop client for Linux built with PyQt6 and Telethon.
Install with `pip install -r requirements.txt`, get your own `api_id`/`api_hash` at
[my.telegram.org](https://my.telegram.org) (API development tools), and run `python3 catgram.py`.
Full chat history loads as you scroll up, photos and static stickers are shown inline,
and a header shows whether a contact is online ("purring") or not.
You can send text and videos (📎 button; install `ffmpeg` for previews and correct video size). Keep your session file private.

