import yt_dlp

def search_media(query, source='sc'):
    search_prefix = 'scsearch6:' if source == 'sc' else 'ytsearch6:'
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'force_generic_extractor': False,
        'youtube_include_dash_manifest': False,
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
                        'audio_url': entry.get('url'), # Для онлайн плеєра
                        'uploader': entry.get('uploader'),
                        'duration': entry.get('duration_string'),
                        'thumbnail': entry.get('thumbnail')
                    })
            return tracks
        except:
            return []

def get_download_opts(format_type, output_path):
    if format_type == 'mp3':
        return {
            'format': 'bestaudio/best',
            'outtmpl': output_path + '.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
    else:
        return {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': output_path + '.mp4',
        }