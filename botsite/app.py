from flask import Flask, render_template, request, send_file, session, after_this_request
import os
import time
from core.downloader import search_media, get_download_opts
from core.telegram_bot import init_bot
import yt_dlp

app = Flask(__name__)
app.secret_key = "super_secret_key"
DOWNLOAD_FOLDER = "downloads"

# Створюємо папку і чистимо її при старті
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)
else:
    for f in os.listdir(DOWNLOAD_FOLDER):
        os.remove(os.path.join(DOWNLOAD_FOLDER, f))

TOKEN = os.environ.get("TELEGRAM_TOKEN")
bot = init_bot(TOKEN)

@app.route('/')
def index():
    return render_template('soundcloud.html')

@app.route('/youtube')
def youtube():
    return render_template('youtube.html')

@app.route('/search', methods=['POST'])
def search():
    query = request.form.get('query')
    source = 'yt' if 'youtube' in request.referrer else 'sc'
    results = search_media(query, source)
    template = 'soundcloud.html' if source == 'sc' else 'youtube.html'
    return render_template(template, tracks=results)

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')
    title = request.form.get('title', 'media')
    fmt = request.form.get('format', 'mp3')
    
    file_id = f"web_{int(time.time())}"
    output_base = os.path.join(DOWNLOAD_FOLDER, file_id)
    opts = get_download_opts(fmt, output_base)
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
        ext = 'mp3' if fmt == 'mp3' else 'mp4'
        final_file = output_base + '.' + ext

    @after_this_request
    def remove_file(response):
        try:
            os.remove(final_file)
        except Exception:
            pass
        return response

    return send_file(final_file, as_attachment=True, download_name=f"{title}.{ext}")

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    site_url = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if site_url:
        bot.set_webhook(url=f"https://{site_url}/{TOKEN}")
    app.run(host='0.0.0.0', port=port)