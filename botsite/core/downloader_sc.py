import yt_dlp

def search_sc(query):
    """Шукає треки на SoundCloud за допомогою yt-dlp"""
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