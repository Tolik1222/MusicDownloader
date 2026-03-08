import requests
import os

# Список робочих серверів Invidious (можна змінювати, якщо один ляже)
INVIDIOUS_INSTANCES = [
    "https://inv.tux.rs",
    "https://invidious.flokinet.to",
    "https://iv.melmac.space"
]

def get_working_instance():
    """Перевіряє доступність серверів і повертає перший робочий"""
    for instance in INVIDIOUS_INSTANCES:
        try:
            response = requests.get(f"{instance}/api/v1/stats", timeout=3)
            if response.status_code == 200:
                return instance
        except:
            continue
    return INVIDIOUS_INSTANCES[0]

def search_media(query, source='sc'):
    if source == 'yt':
        instance = get_working_instance()
        try:
            # Пошук через Invidious API
            search_url = f"{instance}/api/v1/search?q={query}"
            response = requests.get(search_url, timeout=10).json()
            
            tracks = []
            for entry in response[:6]:
                tracks.append({
                    'title': entry.get('title'),
                    'url': f"https://www.youtube.com/watch?v={entry.get('videoId')}",
                    'id': entry.get('videoId'),
                    'uploader': entry.get('author'),
                    'duration': str(entry.get('lengthSeconds')),
                    'thumbnail': entry.get('videoThumbnails', [{}])[0].get('url')
                })
            return tracks
        except Exception as e:
            print(f"Invidious Search error: {e}")
            return []
    
    # Для SoundCloud залишаємо базову заглушку або твій старий код
    return []

def get_invidious_download_url(video_url):
    """Отримує пряме посилання на аудіопотік безпосередньо з Invidious"""
    instance = get_working_instance()
    try:
        # Витягуємо ID відео з посилання
        video_id = video_url.split('v=')[-1].split('&')[0] if 'v=' in video_url else video_url.split('/')[-1]
        
        video_info_url = f"{instance}/api/v1/videos/{video_id}"
        res = requests.get(video_info_url, timeout=10).json()
        
        # Шукаємо найкращий аудіо-потік в adaptiveFormats
        audio_streams = [fmt for fmt in res.get('adaptiveFormats', []) if 'audio' in fmt.get('type', '')]
        
        if audio_streams:
            # Сортуємо за якістю (bitrate) і беремо найкращий
            best_audio = sorted(audio_streams, key=lambda x: int(x.get('bitrate', 0)), reverse=True)[0]
            return best_audio.get('url')
            
        return None
    except Exception as e:
        print(f"Invidious Download error: {e}")
        return None