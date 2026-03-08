import yt_dlp
import os
import time

def get_cookie_path():
    path = os.path.join(os.path.dirname(__file__), '..', 'youtube_cookies.txt')
    return path if os.path.exists(path) else None

def search_media(query, source='sc'):
    search_prefix = 'scsearch6:' if source == 'sc' else 'ytsearch6:'
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'cookiefile': get_cookie_path(), # Додаємо куки тут
    }

def search_media(query, source='sc'):
    search_prefix = 'scsearch6:' if source == 'sc' else 'ytsearch6:'
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'force_generic_extractor': False,
    }

    ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'cookiefile': 'youtube_cookies.txt', # Додай цей рядок обов'язково
}
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"{search_prefix}{query}", download=False)
            tracks = []
            if 'entries' in info:
                for entry in info['entries']:
                    tracks.append({
                        'title': entry.get('title'),
                        'url': entry.get('webpage_url'),
                        'audio_url': entry.get('url'),
                        'uploader': entry.get('uploader'),
                        'duration': entry.get('duration_string'),
                        'thumbnail': entry.get('thumbnail')
                    })
            return tracks
        except Exception:
            return []

def get_download_opts(format_type, output_path):
    if format_type == 'mp3':
        return {
            'format': 'bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
    else: # mp4
        return {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': output_path + '.mp4',
        }
    
    ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'cookiefile': 'youtube_cookies.txt', # Додай цей рядок обов'язково
}