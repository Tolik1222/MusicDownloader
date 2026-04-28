import asyncio
import yt_dlp
import os
import re
import glob
import platform
from typing import Callable, Awaitable

# Прогрес-мітки, що відправляються в Telegram
_PROGRESS_STEPS = {25: False, 50: False, 75: False, 99: False}

DOWNLOADS_DIR = "downloads"


def _ensure_downloads_dir():
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)


def _ffmpeg_path() -> str:
    return os.getcwd() if platform.system() == "Windows" else "/usr/bin"


def _strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def _bar(percent: float) -> str:
    filled = int(percent // 10)
    return "█" * filled + "░" * (10 - filled)


async def async_search_tracks(
    query: str,
    limit: int = 5,
    offset: int = 0,
) -> list[dict]:
    """
    Пошук треків через yt-dlp scsearch.
    Завжди дістає max_search результатів і повертає потрібну сторінку.
    """
    loop = asyncio.get_running_loop()
    max_search = max(offset + limit + 1, 30)

    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True,
    }

    def _search():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"scsearch{max_search}:{query}", download=False)
            entries = info.get('entries', []) if info else []
            page = entries[offset: offset + limit]
            return [
                {
                    'title':    e.get('title', 'Без назви'),
                    'url':      e.get('url') or e.get('webpage_url', ''),
                    'duration': e.get('duration'),
                    'uploader': e.get('uploader'),
                }
                for e in page
            ]

    return await loop.run_in_executor(None, _search)


async def async_download_track(
    url: str,
    progress_callback: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    """
    Завантажує трек та конвертує в MP3.
    Прогрес надсилається лише на позначках 25 / 50 / 75 / 99 %,
    щоб не отримати бан Telegram за спам.
    Повертає абсолютний шлях до MP3-файлу.
    """
    _ensure_downloads_dir()
    loop = asyncio.get_running_loop()

    steps_sent: dict[int, bool] = {25: False, 50: False, 75: False, 99: False}

    def hook(d: dict):
        if d['status'] != 'downloading' or progress_callback is None:
            return

        raw = _strip_ansi(d.get('_percent_str', '0%').strip())
        try:
            pct = float(raw.replace('%', ''))
        except ValueError:
            return

        for threshold in (25, 50, 75, 99):
            if not steps_sent[threshold] and pct >= threshold:
                steps_sent[threshold] = True
                bar = _bar(threshold)
                asyncio.run_coroutine_threadsafe(
                    progress_callback(f"📥 Завантаження: `[{bar}]` {threshold}%"),
                    loop,
                )
                break

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(DOWNLOADS_DIR, '%(id)s.%(ext)s'),  # id замість title → безпечний filename
        'ffmpeg_location': _ffmpeg_path(),
        'progress_hooks': [hook],
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
    }

    def _download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            track_id = info.get('id', '')
            matches = glob.glob(os.path.join(DOWNLOADS_DIR, f"{track_id}*.mp3"))
            if matches:
                return os.path.abspath(matches[0])
            raw_name = ydl.prepare_filename(info)
            mp3_name = os.path.splitext(raw_name)[0] + '.mp3'
            return os.path.abspath(mp3_name)

    return await loop.run_in_executor(None, _download)


def clear_trash():
    """Видаляє всі файли з папки downloads (викликається кожні 10 хв)."""
    if not os.path.isdir(DOWNLOADS_DIR):
        return
    for f in os.listdir(DOWNLOADS_DIR):
        full = os.path.join(DOWNLOADS_DIR, f)
        try:
            if os.path.isfile(full):
                os.remove(full)
        except OSError as e:
            print(f"clear_trash: не вдалося видалити {full}: {e}")