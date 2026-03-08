import requests
import re
import json

def search_yt(query):
    """Шукає відео безпосередньо на сторінці YouTube (працює завжди)"""
    try:
        url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        
        html = requests.get(url, headers=headers, timeout=10).text
        match = re.search(r'var ytInitialData = (.*?);</script>', html)
        if not match:
            return []
            
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
            if len(tracks) >= 6:
                break
                
        return tracks
    except Exception as e:
        print(f"Direct YT Search Error: {e}")
        return []

def get_yt_download_url(video_url):
    """Отримує пряме посилання через ком'юніті-сервери Cobalt (без блокувань IP)"""
    
    # Незалежні сервери, які лояльні до Render
    cobalt_instances = [
        "https://cobalt.q0.is/api/json",
        "https://api.cobalt.best/api/json",
        "https://cobalt.kwiatektv.com/api/json",
        "https://co.wuk.sh/api/json"
    ]
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    data = {
        "url": video_url,
        "isAudioOnly": True,
        "aFormat": "mp3"
    }

    for api in cobalt_instances:
        try:
            res = requests.post(api, headers=headers, json=data, timeout=10)
            if res.status_code == 200:
                result = res.json()
                if 'url' in result:
                    return result['url'] # Повертаємо пряме посилання на файл!
        except Exception as e:
            print(f"Сервер {api} не відповів: {e}")
            continue # Пробуємо наступний сервер у списку
            
    return None