import requests
import re
import json
import yt_dlp

def search_yt(query):
    """Шукає відео безпосередньо на сторінці YouTube"""
    try:
        url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        
        html = requests.get(url, headers=headers, timeout=10).text
        match = re.search(r'var ytInitialData = (.*?);</script>', html)
        if not match: return []
            
        data = json.loads(match.group(1))
        tracks = []
        contents = data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents']
        
        for item in contents:
            if 'videoRenderer' in item:
                vid = item['videoRenderer']
                tracks.append({
                    'title': vid['title']['runs'][0]['text'],
                    'url': f"https://www.youtube.com/watch?v={vid['videoId']}",
                    'id': vid['videoId'],
                    'duration': vid.get('lengthText', {}).get('simpleText', 'N/A'),
                    'thumbnail': vid['thumbnail']['thumbnails'][0]['url'],
                    'uploader': vid['ownerText']['runs'][0]['text'] if 'ownerText' in vid else "YouTube"
                })
            if len(tracks) >= 6: break
        return tracks
    except Exception as e:
        return []

def get_yt_download_url(video_url):
    """Витягує потік через OAuth (TV клієнт)"""
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': False,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['tv', 'android'], 
                'player_skip': ['webpage', 'configs'],
            }
        },
        'username': 'oauth2',
        'password': '',
        'nocheckcertificate': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if 'url' in info:
                return info['url'], "OK"
    except Exception as e:
        return None, f"Помилка: {str(e)}"
    
    return None, "Не вдалося отримати посилання"