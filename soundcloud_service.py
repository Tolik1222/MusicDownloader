import asyncio
import yt_dlp
import os
import time
import re
import platform

async def async_search_tracks(query, limit=5, offset=0):
    """
    Пошук треків з реальною роботою пагінації
    """
    loop = asyncio.get_running_loop()
    
    # Ми просимо yt-dlp знайти фіксовану кількість (наприклад, 20), 
    # щоб користувач міг проклацати хоча б 4 сторінки без затримок.
    max_search = 30 
    search_query = f"scsearch{max_search}:{query}"
    
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await loop.run_in_executor(
            None, 
            lambda: ydl.extract_info(search_query, download=False)
        )
        
        results = []
        if 'entries' in info:
            all_entries = info['entries']
            
            # Ось тут ми беремо "шматочок" для поточної сторінки
            # Якщо offset=0, беремо [0:5], якщо offset=5, беремо [5:10]
            start = offset
            end = offset + limit
            page_entries = all_entries[start:end]
            
            for entry in page_entries:
                results.append({
                    'title': entry.get('title', 'Без назви'),
                    'url': entry.get('url') or entry.get('webpage_url'),
                    'duration': entry.get('duration'),
                    'uploader': entry.get('uploader')
                })
        return results


async def async_download_track(url, progress_callback=None):
    if not os.path.exists('downloads'):
        os.makedirs('downloads')

    loop = asyncio.get_running_loop()

    await asyncio.sleep(1.5)

    def hook(d):
        if d['status'] == 'downloading':
            p_str = d.get('_percent_str', '0%').strip()
            clean_p_str = re.sub(r'\x1b\[[0-9;]*m', '', p_str)

            if progress_callback:
                try:
                    p_val = float(clean_p_str.replace('%', ''))
                    filled = int(p_val // 10)
                    bar = "█" * filled + "░" * (10 - filled)

                    asyncio.run_coroutine_threadsafe(
                        progress_callback(f"📥 Завантаження: `[{bar}]` {clean_p_str}"),
                        loop
                    )
                except:
                    pass

    # шлях до ffmpeg
    if platform.system() == "Windows":
        ffmpeg_path = os.getcwd()
    else:
        ffmpeg_path = "/usr/bin/"

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'ffmpeg_location': ffmpeg_path,
        'progress_hooks': [hook],  # 🔥 важливо
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True
    }

    current_loop = asyncio.get_running_loop()

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await loop.run_in_executor(
            None,
            lambda: ydl.extract_info(url, download=True)
        )

        filename = ydl.prepare_filename(info)
        return filename.rsplit('.', 1)[0] + '.mp3'