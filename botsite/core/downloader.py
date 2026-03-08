import requests
import os
import yt_dlp

INVIDIOUS_INSTANCES = [
    "https://inv.tux.rs",
    "https://invidious.flokinet.to",
    "https://iv.melmac.space"
]

def get_working_instance():
    for instance in INVIDIOUS_INSTANCES:
        try:
            if requests.get(f"{instance}/api/v1/stats", timeout=3).status_code == 200:
                return instance
        except:
            continue
    return INVIDIOUS_INSTANCES[0]

def search_media(query, source='sc'):
    # --- ЛОГІКА ДЛЯ YOUTUBE (через Invidious) ---
    if source == 'yt':
        instance = get_working_instance()
        try:
            search_url = f"{instance}/api/v1/search?q={query}"
            response = requests.get(search_url, timeout=10).json()
            
            tracks = []
            for entry in response[:6]:
                tracks.append({
                    'title': entry.get('title'),
                    'url': f"https://www.youtube.com/watch?v={entry.get('videoId')}",
                    'uploader': entry.get('author'),
                    'duration': str(entry.get('lengthSeconds')),
                    'thumbnail': entry.get('videoThumbnails', [{}])[0].get('url')
                })
            return tracks
        except Exception as e:
            print(f"Invidious Search error: {e}")
            return []

    # --- ЛОГІКА ДЛЯ SOUNDCLOUD (через yt-dlp) ---
    if source == 'sc':
        ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'noplaylist': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(f"scsearch6:{query}", download=False)
                tracks = []
                if 'entries' in info:
                    for entry in info['entries']:
                        tracks.append({
                            'title': entry.get('title'),
                            'url': entry.get('webpage_url'),
                            'uploader': entry.get('uploader'),
                            'duration': entry.get('duration_string'),
                            'thumbnail': entry.get('thumbnail')
                        })
                return tracks
            except Exception as e:
                print(f"SoundCloud Search error: {e}")
                return []
    return []

def get_invidious_download_url(video_url):
    instance = get_working_instance()
    try:
        video_id = video_url.split('v=')[-1].split('&')[0] if 'v=' in video_url else video_url.split('/')[-1]
        res = requests.get(f"{instance}/api/v1/videos/{video_id}", timeout=10).json()
        audio_streams = [fmt for fmt in res.get('adaptiveFormats', []) if 'audio' in fmt.get('type', '')]
        if audio_streams:
            return sorted(audio_streams, key=lambda x: int(x.get('bitrate', 0)), reverse=True)[0].get('url')
        return None
    except Exception as e:
        print(f"Invidious Download error: {e}")
        return None