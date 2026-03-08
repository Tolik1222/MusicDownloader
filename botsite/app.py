from flask import Flask, render_template, request, send_file, session, after_this_request, redirect
import os
import time
import requests
from core.downloader import search_media, get_invidious_download_url
from core.telegram_bot import init_bot
import telebot

app = Flask(__name__)
app.secret_key = "super_secret_key"
DOWNLOAD_FOLDER = "downloads"

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
bot = init_bot(TOKEN)

@app.route('/')
def index():
    return render_template('soundcloud.html')

@app.route('/youtube')
def youtube():
    return render_template('youtube.html')

@app.route('/search_sc', methods=['POST'])
def search_sc():
    query = request.form.get('query')
    try:
        results = search_media(query, source='sc')
    except Exception as e:
        print(f"Помилка пошуку SoundCloud: {e}")
        results = []
    return render_template('soundcloud.html', tracks=results)

@app.route('/search_yt', methods=['POST'])
def search_yt():
    query = request.form.get('query')
    try:
        results = search_media(query, source='yt')
    except Exception as e:
        print(f"Помилка пошуку Youtube: {e}")
        results = []
    return render_template('youtube.html', tracks=results)

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')
    fmt = request.form.get('format', 'mp3')
    is_audio = (fmt == 'mp3')

    download_link = get_invidious_download_url(url)
    
    if not download_link:
        return "Помилка: Не вдалося отримати посилання для завантаження", 500

    return redirect(download_link)

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
    if site_url:
        bot.remove_webhook()
        time.sleep(1) 
        bot.set_webhook(url=f"https://{site_url}/{TOKEN}")
        print(f"Webhook set to: https://{site_url}/{TOKEN}")
    
    app.run(host='0.0.0.0', port=port)