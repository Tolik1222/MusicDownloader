import os
import asyncio
import threading
import time
from flask import Flask, render_template, request, send_file, session
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

# Імпортуємо твої модулі
import soundcloud_service as sc
from bot import router 
import DB  # Твій файл DB.py

# Завантажуємо налаштування
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
SECRET_KEY = os.getenv('SECRET_KEY', 'dev_secret')

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Налаштування бота
bot = Bot(token=TOKEN)
dp = Dispatcher()
dp.include_router(router)

# --- ФОНОВІ ФУНКЦІЇ ---

def run_auto_clean():
    """Потік для видалення старих файлів"""
    while True:
        try:
            sc.clear_trash()
        except Exception as e:
            print(f"Помилка очищення: {e}")
        time.sleep(600)

def run_bot():
    """Потік для запуску Telegram бота"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Спочатку ініціалізуємо базу
    loop.run_until_complete(DB.init_db())
    
    # ВИДАЛЯЄМО ВЕБХУК, щоб не було конфлікту (додано цей рядок)
    print("🧹 Видаляємо старий вебхук...")
    loop.run_until_complete(bot.delete_webhook(drop_pending_updates=True))
    
    print("🤖 Бот запущений у режимі Polling")
    loop.run_until_complete(dp.start_polling(bot, handle_signals=False))
# --- МАРШРУТИ FLASK (WEB) ---

@app.route('/')
async def index():
    # Отримуємо історію з DB.py (загальна історія)
    history = await DB.get_user_history(limit=10) 
    return render_template('index.html', history=history)

@app.route('/search', methods=['POST'])
async def search():
    query = request.form.get('query')
    results = await sc.async_search_tracks(query)
    history = await DB.get_user_history(limit=10)
    return render_template('index.html', tracks=results, query=query, history=history)

@app.route('/download', methods=['POST'])
async def download():
    url = request.form.get('url')
    title = request.form.get('title')
    
    file_path = await sc.async_download_track(url)
    
    # Записуємо скачування з сайту в базу (id 0)
    await DB.add_to_history(0, title, url)
    
    return send_file(file_path, as_attachment=True, download_name=f"{title}.mp3")

# --- ЗАПУСК ПРОЄКТУ ---

if __name__ == '__main__':
    # 1. Запускаємо потік з ботом та базою даних
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # 2. Запускаємо потік очищення
    clean_thread = threading.Thread(target=run_auto_clean, daemon=True)
    clean_thread.start()
    
    # 3. Запускаємо веб-сервер
    print("🚀 Сервер та бот запускаються...")
    port = int(os.environ.get("PORT", 10000))
    # Вимикаємо debug, щоб потоки не запускалися двічі
    app.run(host='0.0.0.0', port=port, debug=False)