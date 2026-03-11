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
        'format_sort': ['ext:mp3', 'ext:m4a', 'acodec:mp3'],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(query, download=False)
            tracks = []
            if 'entries' in info:
                for entry in info['entries']:
                    formats = entry.get('formats', [])
                    audio_url = entry.get('url')
                    
                    for f in formats:
                        if f.get('protocol') == 'https' and f.get('ext') in ['mp3', 'm4a']:
                            audio_url = f.get('url')
                            break

                    tracks.append({
                        'title': entry.get('title'),
                        'url': entry.get('webpage_url'),
                        'audio_url': audio_url,
                        'uploader': entry.get('uploader'),
                        'duration': entry.get('duration_string'),
                        'thumbnail': entry.get('thumbnail')
                    })
            return tracks
        except Exception as e:
            logging.error(f"SC Search Error: {e}")
            return []

def download_track(url):
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)
        
    file_path = os.path.join(DOWNLOAD_FOLDER, f"track_{int(time.time())}")
    
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