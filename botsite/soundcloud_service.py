import yt_dlp
import os
import time
import logging

DOWNLOAD_FOLDER = 'temp_downloads'

def search_tracks(query, limit=6):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': f'scsearch{limit}:', 
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info:
                return [{
                    'title': e.get('title'),
                    'url': e.get('webpage_url'),
                    'audio_url': e.get('url'),
                    'uploader': e.get('uploader'),
                    'duration': e.get('duration_string'),
                    'thumbnail': e.get('thumbnail')
                } for e in info['entries']]
            return []
        except Exception as e:
            logging.error(f"SC Search Error: {e}")
            return []

def download_track(url):
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)
        
    file_id = int(time.time())
    file_path = os.path.join(DOWNLOAD_FOLDER, f"track_{file_id}")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': file_path + '.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192'
        }],
        'quiet': True
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return file_path + ".mp3"