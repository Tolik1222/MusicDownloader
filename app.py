import os
import asyncio
import threading
import time

from quart import Quart, render_template, request, send_file
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

import soundcloud_service as sc
from bot import router
import DB

load_dotenv()

TOKEN = os.getenv('TELEGRAM_TOKEN')
SECRET_KEY = os.getenv('SECRET_KEY', 'dev_secret')

# Quart — async-сумісна версія Flask (той самий API, ті самі шаблони)
app = Quart(__name__)
app.secret_key = SECRET_KEY

bot = Bot(token=TOKEN)
dp = Dispatcher()
dp.include_router(router)


# ---------------------------------------------------------------------------
# Фонові потоки
# ---------------------------------------------------------------------------

def run_auto_clean():
    """Видаляє старі файли кожні 10 хвилин."""
    while True:
        try:
            sc.clear_trash()
        except Exception as e:
            print(f"[auto_clean] помилка: {e}")
        time.sleep(600)


def run_bot():
    """Запускає Telegram-бота у власному event loop (окремий потік)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(DB.init_db())

    print("🧹 Видаляємо старий вебхук...")
    loop.run_until_complete(bot.delete_webhook(drop_pending_updates=True))

    print("🤖 Бот запущений у режимі Polling")
    loop.run_until_complete(dp.start_polling(bot, handle_signals=False))


# ---------------------------------------------------------------------------
# Ініціалізація БД при старті Quart
# ---------------------------------------------------------------------------

@app.before_serving
async def startup():
    await DB.init_db()


# ---------------------------------------------------------------------------
# Маршрути
# ---------------------------------------------------------------------------

@app.route('/')
async def index():
    # get_recent_history — без user_id, загальна стрічка
    history = await DB.get_recent_history(limit=10)
    return await render_template('index.html', history=history)


@app.route('/search', methods=['POST'])
async def search():
    form = await request.form
    query = form.get('query', '').strip()
    results = await sc.async_search_tracks(query) if query else []
    history = await DB.get_recent_history(limit=10)
    return await render_template('index.html', tracks=results, query=query, history=history)


@app.route('/download', methods=['POST'])
async def download():
    form = await request.form
    url   = form.get('url', '')
    title = form.get('title', 'track')

    file_path = await sc.async_download_track(url)

    # user_id = 0 означає завантаження з сайту
    await DB.add_to_history(0, title, url)

    return await send_file(
        file_path,
        as_attachment=True,
        attachment_filename=f"{title}.mp3",
    )


# ---------------------------------------------------------------------------
# Точка входу
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # 1. Бот у фоновому потоці
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # 2. Авто-очищення у фоновому потоці
    clean_thread = threading.Thread(target=run_auto_clean, daemon=True)
    clean_thread.start()

    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Сервер запускається на порту {port}...")

    # Quart можна запускати напряму або через hypercorn/uvicorn
    app.run(host='0.0.0.0', port=port, debug=False)