import os
import hashlib
import hmac
import asyncio
import threading
import time
from functools import wraps

from quart import (
    Quart, render_template, request,
    send_file, redirect, url_for, session, jsonify
)
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

import soundcloud_service as sc
from bot import router, ITEMS_PER_PAGE
import DB

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

TOKEN        = os.getenv('TELEGRAM_TOKEN', '')
SECRET_KEY   = os.getenv('SECRET_KEY', 'dev_secret_change_me')
BOT_USERNAME = os.getenv('BOT_USERNAME', '').strip().lstrip('@')  # ім'я бота без @, напр. MySoundBot
ADMIN_IDS    = [
    int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()
]

app = Quart(__name__)
app.secret_key = SECRET_KEY

bot_instance = Bot(token=TOKEN)
dp = Dispatcher()
dp.include_router(router)


# Помічники

def current_user() -> dict | None:
    return session.get('user')

def is_admin() -> bool:
    u = current_user()
    return u is not None and int(u['id']) in ADMIN_IDS

def login_required(fn):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for('login_page'))
        return await fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        if not is_admin():
            return await render_template('403.html'), 403
        return await fn(*args, **kwargs)
    return wrapper


# Telegram Login перевірка 

def verify_telegram_login(data: dict) -> bool:
    check_hash = data.pop('hash', '')
    data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hashlib.sha256(TOKEN.encode()).digest()
    computed   = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, check_hash)


# Фонові потоки 

def run_auto_clean():
    while True:
        try:
            sc.clear_trash()
        except Exception as e:
            print(f"[auto_clean] {e}")
        time.sleep(600)

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(DB.init_db())
    print("🧹 Видаляємо старий вебхук...")
    loop.run_until_complete(bot_instance.delete_webhook(drop_pending_updates=True))
    print("🤖 Бот запущений у режимі Polling")
    loop.run_until_complete(dp.start_polling(bot_instance, handle_signals=False))


@app.before_serving
async def startup():
    await DB.init_db()


#  Auth 

@app.route('/login')
async def login_page():
    if current_user():
        return redirect(url_for('index'))
    auth_url = url_for('telegram_auth', _external=True)
    return await render_template('login.html', bot_username=BOT_USERNAME, auth_url=auth_url)

@app.route('/auth/telegram')
async def telegram_auth():
    data = dict(request.args)
    auth_date = int(data.get('auth_date', 0))

    if not verify_telegram_login(data):
        return "Невірний підпис від Telegram.", 403

    if time.time() - auth_date > 86400:
        return "Дані застаріли. Спробуйте ще раз.", 403

    user_id    = int(request.args.get('id', 0))
    username   = request.args.get('username')
    first_name = request.args.get('first_name', 'User')
    photo_url  = request.args.get('photo_url', '')

    await DB.add_user(user_id, username, first_name)
    
    session['user'] = {
        'id': user_id,
        'username': username,
        'first_name': first_name,
        'photo_url': photo_url,
    }
    
    return redirect('/')

@app.route('/logout')
async def logout():
    session.clear()
    return redirect(url_for('login_page'))


#  Головна 

@app.route('/')
@login_required
async def index():
    user    = current_user()
    history = await DB.get_user_history(user['id'], limit=20)
    auth_url = url_for('telegram_auth', _external=True)
    return await render_template(
        'index.html',
        user=user,
        history=history,
        is_admin=is_admin(),
        bot_username=BOT_USERNAME,
        auth_url=auth_url,
    )

@app.route('/search', methods=['GET', 'POST'])
@login_required
async def search():
    if request.method == 'POST':
        form = await request.form
        query = form.get('query', '').strip()
        page_raw = form.get('page', '1')
    else:
        query = request.args.get('query', '').strip()
        page_raw = request.args.get('page', '1')

    try:
        page = max(1, int(page_raw))
    except (TypeError, ValueError):
        page = 1

    offset = (page - 1) * ITEMS_PER_PAGE

    if query:
        results = await sc.async_search_tracks(
            query,
            limit=ITEMS_PER_PAGE + 1,
            offset=offset,
        )
    else:
        results = []

    has_next = len(results) > ITEMS_PER_PAGE
    tracks = results[:ITEMS_PER_PAGE]
    user    = current_user()
    history = await DB.get_user_history(user['id'], limit=20)
    auth_url = url_for('telegram_auth', _external=True)
    return await render_template(
        'index.html',
        user=user,
        tracks=tracks,
        query=query,
        page=page,
        has_prev=page > 1,
        has_next=has_next,
        history=history,
        is_admin=is_admin(),
        bot_username=BOT_USERNAME,
        auth_url=auth_url,
    )

@app.route('/download', methods=['POST'])
@login_required
async def download():
    form      = await request.form
    url       = form.get('url', '')
    title     = form.get('title', 'track')
    user      = current_user()
    file_path = await sc.async_download_track(url)
    await DB.add_to_history(user['id'], title, url)
    return await send_file(
        file_path,
        as_attachment=True,
        attachment_filename=f"{title}.mp3",
    )


#  Адмінка 

@app.route('/admin')
@login_required
@admin_required
async def admin_panel():
    total_users, total_downloads = await DB.get_stats()
    all_downloads = await DB.admin_get_all_downloads(limit=300)
    all_users     = await DB.admin_get_all_users()
    top_tracks    = await DB.admin_get_top_tracks(limit=10)
    by_day        = await DB.admin_get_downloads_by_day(days=30)
    new_users     = await DB.admin_get_new_users_by_day(days=30)

    return await render_template(
        'admin.html',
        user=current_user(),
        stats={'users': total_users, 'downloads': total_downloads},
        all_downloads=all_downloads,
        all_users=all_users,
        top_tracks=top_tracks,
        by_day=by_day,
        new_users=new_users,
        bot_username=BOT_USERNAME,
    )

@app.route('/admin/delete/<int:record_id>', methods=['POST'])
@login_required
@admin_required
async def admin_delete(record_id: int):
    await DB.admin_delete_history_record(record_id)
    return jsonify({'ok': True})


#  Запуск 

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=run_auto_clean, daemon=True).start()
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Сервер на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False)