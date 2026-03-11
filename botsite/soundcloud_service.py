import yt_dlp
import os
import time
import zipfile

DOWNLOAD_FOLDER = 'temp_downloads'

def search_tracks(query, limit=6, offset=0):
    total = limit + offset
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': f'scsearch{total}:',
        'format_sort': ['ext:mp3', 'ext:m4a'],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(query, download=False)
            entries = info.get('entries', [])[offset:]
            return [{
                'title': e.get('title'),
                'url': e.get('webpage_url'),
                'audio_url': e.get('url'),
                'uploader': e.get('uploader'),
                'duration': e.get('duration_string'),
                'thumbnail': e.get('thumbnail')
            } for e in entries]
        except: return []

def download_track(url):
    if not os.path.exists(DOWNLOAD_FOLDER): os.makedirs(DOWNLOAD_FOLDER)
    file_path = os.path.join(DOWNLOAD_FOLDER, f"track_{int(time.time())}")
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': file_path + '.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
        'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return file_path + ".mp3"

def create_zip(file_paths):
    zip_path = os.path.join(DOWNLOAD_FOLDER, f"archive_{int(time.time())}.zip")
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for f in file_paths:
            if os.path.exists(f): zipf.write(f, os.path.basename(f))
    return zip_path

def clear_trash():
    now = time.time()
    if os.path.exists(DOWNLOAD_FOLDER):
        for f in os.listdir(DOWNLOAD_FOLDER):
            p = os.path.join(DOWNLOAD_FOLDER, f)
            if os.path.isfile(p) and now - os.path.getmtime(p) > 900:
                try: os.remove(p)
                except: pass