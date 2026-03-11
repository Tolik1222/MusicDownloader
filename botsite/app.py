import os
import telebot
from flask import Flask, render_template, request, send_file, session, jsonify
import soundcloud_service as sc
import bot as bot_module
import threading
import time

TOKEN = os.environ.get('TELEGRAM_TOKEN')
HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret')
bot = telebot.TeleBot(TOKEN)
bot_module.register_handlers(bot)

def auto_clean():
    while True:
        sc.clear_trash()
        time.sleep(600)

threading.Thread(target=auto_clean, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html', history=session.get('download_history', []))

@app.route('/search', methods=['POST'])
def search():
    query = request.form.get('query')
    results = sc.search_tracks(query)
    return render_template('index.html', tracks=results, query=query, history=session.get('download_history', []))

@app.route('/search_more', methods=['POST'])
def search_more():
    data = request.json
    results = sc.search_tracks(data.get('query'), limit=6, offset=data.get('offset', 6))
    return jsonify({"tracks": results})

@app.route('/download', methods=['POST'])
def download():
    url, title = request.form.get('url'), request.form.get('title')
    history = session.get('download_history', [])
    if title not in history:
        history.insert(0, title)
        session['download_history'] = history[:5]
    file_path = sc.download_track(url)
    return send_file(file_path, as_attachment=True, download_name=f"{title}.mp3")


@app.route('/download_zip', methods=['POST'])
def download_zip():
    data = request.json
    urls = data.get('urls', [])
    titles = data.get('titles', [])
    
    if not urls:
        return jsonify({"error": "No tracks selected"}), 400
    
    downloaded_files = []
    try:
        for url in urls:
            file_path = sc.download_track(url)
            downloaded_files.append(file_path)
        
        zip_path = sc.create_zip(downloaded_files)

        for f in downloaded_files:
            if os.path.exists(f): os.remove(f)
            
        return send_file(zip_path, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

if __name__ == '__main__':
    if HOSTNAME:
        bot.remove_webhook()
        bot.set_webhook(url=f"https://{HOSTNAME}/{TOKEN}")
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))