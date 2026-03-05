from flask import Flask, render_template, request, send_file, session
import yt_dlp
import os
import time
import logging

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_session' # Потрібно для роботи сесій

log_path = r'errors.log'
logging.basicConfig(filename=log_path, level=logging.ERROR, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

DOWNLOAD_FOLDER = 'temp_downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def search_soundcloud(query):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': 'scsearch6:', 
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(query, download=False)
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
            logging.error(f"Помилка пошуку для запиту '{query}': {str(e)}")
            return []

@app.route('/')
def index():
    # Отримуємо історію з сесії або пустий список
    history = session.get('download_history', [])
    return render_template('index.html', history=history)

@app.route('/search', methods=['POST'])
def search():
    query = request.form.get('query')
    results = search_soundcloud(query)
    history = session.get('download_history', [])
    if results:
        return render_template('index.html', tracks=results, history=history)
    return render_template('index.html', error="Нічого не знайдено", history=history)

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')
    title = request.form.get('title')

    history = session.get('download_history', [])
    if title not in history:
        history.insert(0, title)
        session['download_history'] = history[:5]

    timestamp = int(time.time())
    file_path = os.path.join(DOWNLOAD_FOLDER, f"track_{timestamp}")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': file_path + '.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return send_file(file_path + ".mp3", as_attachment=True, download_name=f"{title}.mp3")
    except Exception as e:
        logging.error(f"Помилка завантаження треку '{title}' ({url}): {str(e)}")
        return f"Помилка: {str(e)}"

if __name__ == '__main__':
    app.run(debug=True)