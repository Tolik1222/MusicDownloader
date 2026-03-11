import os
import telebot
from flask import Flask, render_template, request, send_file, session
import soundcloud_service as sc
import bot as bot_module

TOKEN = os.environ.get('TELEGRAM_TOKEN')
HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key')
bot = telebot.TeleBot(TOKEN)

bot_module.register_handlers(bot)

@app.route('/')
def index():
    return render_template('index.html', history=session.get('download_history', []))

@app.route('/search', methods=['POST'])
def web_search():
    query = request.form.get('query')
    results = sc.search_tracks(query)
    return render_template('index.html', tracks=results, history=session.get('download_history', []))

@app.route('/download', methods=['POST'])
def web_download():
    url = request.form.get('url')
    title = request.form.get('title')
    
    history = session.get('download_history', [])
    if title not in history:
        history.insert(0, title)
        session['download_history'] = history[:5]

    file_path = sc.download_track(url)
    return send_file(file_path, as_attachment=True, download_name=f"{title}.mp3")

@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
    bot.process_new_updates([update])
    return "OK", 200

if __name__ == '__main__':
    if HOSTNAME:
        bot.remove_webhook()
        bot.set_webhook(url=f"https://{HOSTNAME}/{TOKEN}")
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)