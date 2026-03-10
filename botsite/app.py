from flask import Flask, render_template, request, redirect, Response, stream_with_context
import os
import time
import requests
import telebot
from core.telegram_bot import init_bot

app = Flask(__name__)
app.secret_key = "super_secret_key"
TOKEN = os.environ.get("TELEGRAM_TOKEN")
bot = init_bot(TOKEN)

@app.route('/')
def index(): return render_template('soundcloud.html')

@app.route('/youtube')
def youtube(): return render_template('youtube.html')

@app.route('/search_sc', methods=['POST'])
def route_search_sc():
    query = request.form.get('query')
    from core.downloader_sc import search_sc
    return render_template('soundcloud.html', tracks=search_sc(query))

@app.route('/search_yt', methods=['POST'])
def route_search_yt():
    query = request.form.get('query')
    from core.downloader_yt import search_yt
    return render_template('youtube.html', tracks=search_yt(query))

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')
    
    if "youtube.com" in url or "youtu.be" in url:
        from core.downloader_yt import get_yt_download_url
        download_link, debug_info = get_yt_download_url(url)
        
        if not download_link:
            return f"<h3>Помилка завантаження</h3><p>{debug_info}</p>", 500
            
        # ПРОКСІ: Сервер Render качає аудіо і стрімить тобі.
        try:
            req = requests.get(download_link, stream=True)
            return Response(
                stream_with_context(req.iter_content(chunk_size=8192)),
                headers={
                    'Content-Disposition': 'attachment; filename="youtube_track.m4a"',
                    'Content-Type': 'audio/mp4'
                }
            )
        except Exception as e:
            return f"Помилка передачі файлу: {e}", 500
            
    return "Невідоме посилання або розробляється", 400

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    return "Forbidden", 403

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    site_url = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if site_url and TOKEN:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=f"https://{site_url}/{TOKEN}")
    app.run(host='0.0.0.0', port=port)