import asyncio
import yt_dlp
import os
import re
import glob
import platform
import shutil
from typing import Callable, Awaitable

# Патч для SoundcloudPlaylistBaseIE в yt-dlp, щоб підтягувати назви треків у плоскому плейлисті
try:
    from yt_dlp.extractor.soundcloud import SoundcloudPlaylistBaseIE
    original_extract_set = SoundcloudPlaylistBaseIE._extract_set

    def patched_extract_set(self, playlist, token=None):
        original_url_result = self.url_result
        tracks = playlist.get('tracks') or []
        title_map = {}
        for t in tracks:
            tid = t.get('id')
            title = t.get('title')
            if tid and title:
                title_map[str(tid)] = title
                
        def custom_url_result(url, ie=None, video_id=None, video_title=None, **kwargs):
            if not video_title and video_id:
                video_title = title_map.get(str(video_id))
            return original_url_result(url, ie=ie, video_id=video_id, video_title=video_title, **kwargs)
            
        self.url_result = custom_url_result
        try:
            return original_extract_set(self, playlist, token)
        finally:
            self.url_result = original_url_result

    SoundcloudPlaylistBaseIE._extract_set = patched_extract_set
except Exception as patch_err:
    print(f"[soundcloud_service] не вдалося застосувати патч плейлистів: {patch_err}")

# Прогрес-мітки, що відправляються в Telegram
_PROGRESS_STEPS = {25: False, 50: False, 75: False, 99: False}

DOWNLOADS_DIR = "downloads"


def _get_ydl_opts(extra_opts: dict | None = None) -> dict:
    """
    Повертає базові оптимізовані налаштування для yt-dlp.
    - js_runtimes та remote_components: для обходу JS-challenge та уникнення обмежень швидкості (throttling).
    - concurrent_fragment_downloads та http_chunk_size: для максимально швидкого завантаження.
    """
    opts = {
        'quiet': True,
        'js_runtimes': {'node': {}},
        'remote_components': ['ejs:github'],
        'nokeepalive': True,
        'concurrent_fragment_downloads': 8,
        'http_chunk_size': 10485760,  # 10 MB
    }
    if extra_opts:
        opts.update(extra_opts)
    return opts


def _ensure_downloads_dir():
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)


def _ensure_ffmpeg(
    loop: asyncio.AbstractEventLoop | None = None,
    progress_callback: Callable[[str], Awaitable[None]] | None = None,
) -> str | None:
    """
    Перевіряє наявність ffmpeg та ffprobe.
    1. Перевіряє системний PATH.
    2. Перевіряє поточну директорію.
    3. Якщо Windows і не знайдено, автоматично завантажує static-збірку з gyan.dev.
    """
    # 1. Перевірка в системному PATH
    ffmpeg_in_path = shutil.which("ffmpeg")
    ffprobe_in_path = shutil.which("ffprobe")
    if ffmpeg_in_path and ffprobe_in_path:
        return None  # Дозволити yt-dlp шукати в PATH автоматично

    # 2. Перевірка в поточній директорії
    cwd = os.getcwd()
    suffix = ".exe" if platform.system() == "Windows" else ""
    ffmpeg_local = os.path.join(cwd, f"ffmpeg{suffix}")
    ffprobe_local = os.path.join(cwd, f"ffprobe{suffix}")
    
    if os.path.isfile(ffmpeg_local) and os.path.isfile(ffprobe_local):
        return cwd

    # 3. Якщо це Windows і файли відсутні, завантажуємо
    if platform.system() == "Windows":
        if progress_callback and loop:
            asyncio.run_coroutine_threadsafe(
                progress_callback("⏳ Компоненти FFmpeg/FFprobe не знайдені. Завантажую їх автоматично (~37 MB)..."),
                loop
            )
        try:
            import urllib.request
            import zipfile
            import io

            print("FFmpeg/FFprobe not found. Downloading static build from gyan.dev...")
            url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=120) as response:
                zip_data = response.read()

            with zipfile.ZipFile(io.BytesIO(zip_data)) as zip_ref:
                for file_info in zip_ref.infolist():
                    filename = os.path.basename(file_info.filename)
                    if filename in ("ffmpeg.exe", "ffprobe.exe"):
                        target_path = os.path.join(cwd, filename)
                        with zip_ref.open(file_info) as source, open(target_path, "wb") as target:
                            shutil.copyfileobj(source, target)
                            
            if progress_callback and loop:
                asyncio.run_coroutine_threadsafe(
                    progress_callback("✅ Компоненти FFmpeg успішно завантажені! Починаємо завантаження треку..."),
                    loop
                )
            return cwd
        except Exception as e:
            print(f"[_ensure_ffmpeg] Помилка завантаження: {e}")
            if progress_callback and loop:
                asyncio.run_coroutine_threadsafe(
                    progress_callback(f"⚠️ Помилка автоматичного завантаження FFmpeg: {e}. Будь ласка, встановіть його вручну."),
                    loop
                )

    # Для Linux/macOS за замовчуванням повертаємо /usr/bin
    if platform.system() != "Windows":
        return "/usr/bin"
        
    return None


def _strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def _bar(percent: float) -> str:
    filled = int(percent // 10)
    return "█" * filled + "░" * (10 - filled)


def is_valid_url(text: str) -> bool:
    """Перевіряє, чи є текст валідним посиланням SoundCloud або YouTube."""
    text_lower = text.strip().lower()
    return (
        "soundcloud.com/" in text_lower or
        "youtube.com/" in text_lower or
        "youtu.be/" in text_lower or
        "music.youtube.com/" in text_lower
    )


async def async_get_track_metadata(url: str) -> dict | None:
    """Отримує метадані для одного треку за посиланням за допомогою yt-dlp."""
    loop = asyncio.get_running_loop()
    ydl_opts = _get_ydl_opts({
        'skip_download': True,
    })
    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None
                return {
                    'title':    info.get('title', 'Без назви'),
                    'url':      info.get('webpage_url') or info.get('url') or url,
                    'duration': info.get('duration'),
                    'uploader': info.get('uploader') or info.get('artist'),
                }
            except Exception as e:
                print(f"[async_get_track_metadata] помилка: {e}")
                return None
    return await loop.run_in_executor(None, _extract)


async def async_search_tracks(
    query: str,
    limit: int = 5,
    offset: int = 0,
    source: str = 'soundcloud',
) -> list[dict]:
    """
    Пошук треків через yt-dlp за допомогою scsearch (SoundCloud) або ytsearch (YouTube).
    Завжди дістає max_search результатів і повертає потрібну сторінку.
    """
    loop = asyncio.get_running_loop()
    max_search = max(offset + limit + 1, 30)

    is_youtube = source == 'youtube'
    clean_query = query.strip()
    if clean_query.lower().startswith(('yt:', 'ютуб:', 'youtube:')):
        is_youtube = True
        clean_query = re.sub(r'^(yt:|ютуб:|youtube:)\s*', '', clean_query, flags=re.IGNORECASE)

    prefix = "ytsearch" if is_youtube else "scsearch"

    ydl_opts = _get_ydl_opts({
        'extract_flat': True,
        'skip_download': True,
    })

    def _search():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(f"{prefix}{max_search}:{clean_query}", download=False)
                entries = info.get('entries', []) if info else []
                page = entries[offset: offset + limit]
                return [
                    {
                        'title':    e.get('title', 'Без назви'),
                        'url':      e.get('url') or e.get('webpage_url') or (f"https://www.youtube.com/watch?v={e.get('id')}" if e.get('id') else ''),
                        'duration': e.get('duration'),
                        'uploader': e.get('uploader'),
                    }
                    for e in page
                ]
            except Exception as e:
                print(f"[async_search_tracks] помилка пошуку: {e}")
                return []

    return await loop.run_in_executor(None, _search)


_download_locks = {}
_locks_lock = asyncio.Lock()

async def _get_url_lock(url: str) -> asyncio.Lock:
    async with _locks_lock:
        if url not in _download_locks:
            _download_locks[url] = asyncio.Lock()
        return _download_locks[url]


async def async_download_track(
    url: str,
    progress_callback: Callable[[str], Awaitable[None]] | None = None,
    as_video: bool = False,
) -> tuple[str, str]:
    """
    Завантажує трек (конвертує в MP3) або відео (MP4).
    Прогрес надсилається лише на позначках 25 / 50 / 75 / 99 %,
    щоб не отримати бан Telegram за спам.
    Повертає кортеж (абсолютний шлях до файлу, назва треку/відео).
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

    ydl_opts = _get_ydl_opts({
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' if as_video else 'bestaudio/best',
        'outtmpl': os.path.join(DOWNLOADS_DIR, '%(id)s.%(ext)s'),  # id замість title → безпечний filename
        'noplaylist': True,
        'progress_hooks': [hook],
    })

    if not as_video:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    ffmpeg_dir = _ensure_ffmpeg(loop, progress_callback)
    if ffmpeg_dir:
        ydl_opts['ffmpeg_location'] = ffmpeg_dir

    def _download():
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Спочатку перевіряємо, чи файл вже існує, без завантаження
                try:
                    meta = ydl.extract_info(url, download=False)
                    track_id = meta.get('id', '')
                    track_title = meta.get('title', 'track')
                    if track_id:
                        matches = glob.glob(os.path.join(DOWNLOADS_DIR, f"{track_id}.*"))
                        valid_matches = [m for m in matches if not m.endswith(('.part', '.ytdl', '.temp'))]
                        for match in valid_matches:
                            ext = os.path.splitext(match)[1].lower()
                            is_video_ext = ext in ('.mp4', '.mkv', '.webm', '.avi', '.mov')
                            if (as_video and is_video_ext) or (not as_video and ext == '.mp3'):
                                return os.path.abspath(match), track_title
                except Exception as meta_err:
                    print(f"[_download] Не вдалося отримати метадані перед завантаженням: {meta_err}")

                # Якщо файлу немає, виконуємо завантаження
                info = ydl.extract_info(url, download=True)
                track_title = info.get('title', 'track')
                track_id = info.get('id', '')
                
                # Пошук файлу за id, щоб отримати правильне розширення
                matches = glob.glob(os.path.join(DOWNLOADS_DIR, f"{track_id}.*"))
                valid_matches = [m for m in matches if not m.endswith(('.part', '.ytdl', '.temp'))]
                if valid_matches:
                    return os.path.abspath(valid_matches[0]), track_title

                raw_name = ydl.prepare_filename(info)
                ext = 'mp3' if not as_video else (info.get('ext') or 'mp4')
                target_name = os.path.splitext(raw_name)[0] + f'.{ext}'
                if os.path.exists(target_name):
                    return os.path.abspath(target_name), track_title
                return os.path.abspath(raw_name), track_title
        except Exception as e:
            err_msg = str(e)
            if "DRM protected" in err_msg or "drm" in err_msg.lower():
                raise ValueError("DRM_PROTECTED")
            raise e

    lock = await _get_url_lock(url)
    async with lock:
        return await loop.run_in_executor(None, _download)


async def async_get_url_info(url: str) -> dict | None:
    """
    Визначає тип посилання (трек чи плейлист) та повертає метадані.
    Повертає dict з ключем 'type': 'track' або 'playlist'.
    """
    loop = asyncio.get_running_loop()
    ydl_opts = _get_ydl_opts({
        'extract_flat': True,
        'skip_download': True,
    })
    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None
                
                # Перевіряємо, чи це плейлист
                if info.get('_type') == 'playlist' or 'entries' in info:
                    raw_entries = info.get('entries', [])
                    tracks = []
                    for idx, e in enumerate(raw_entries):
                        if not e:
                            continue
                        tracks.append({
                            'id':       e.get('id'),
                            'title':    e.get('title', 'Без назви'),
                            'url':      e.get('url') or e.get('webpage_url') or (f"https://soundcloud.com/{e.get('uploader')}/{e.get('id')}" if e.get('id') and e.get('uploader') else ''),
                            'duration': e.get('duration'),
                            'uploader': e.get('uploader') or e.get('artist') or 'SoundCloud',
                            'index':    idx,
                        })
                    return {
                        'type': 'playlist',
                        'title': info.get('title', 'Плейлист'),
                        'id': info.get('id') or str(hash(url)),
                        'tracks': tracks,
                    }
                else:
                    return {
                        'type': 'track',
                        'title':    info.get('title', 'Без назви'),
                        'url':      info.get('webpage_url') or info.get('url') or url,
                        'duration': info.get('duration'),
                        'uploader': info.get('uploader') or info.get('artist') or 'SoundCloud',
                        'id':       info.get('id'),
                    }
            except Exception as e:
                print(f"[async_get_url_info] помилка: {e}")
                return None
                
    return await loop.run_in_executor(None, _extract)


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