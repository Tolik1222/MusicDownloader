import os
import re
import hashlib
import hmac
import asyncio
import threading
import time
from functools import wraps

from quart import (
    Quart, render_template, request,
    send_file, redirect, url_for, session, jsonify, Response
)
import urllib.parse
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

import soundcloud_service as sc
import stb_service as stb
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
app.config["RESPONSE_TIMEOUT"] = None  # Відключаємо ліміт у 60 секунд для стрімінгу великих файлів

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
        source='soundcloud',
    )

@app.route('/search', methods=['GET', 'POST'])
@login_required
async def search():
    if request.method == 'POST':
        form = await request.form
        query = form.get('query', '').strip()
        page_raw = form.get('page', '1')
        source = form.get('source', 'soundcloud').strip()
    else:
        query = request.args.get('query', '').strip()
        page_raw = request.args.get('page', '1')
        source = request.args.get('source', 'soundcloud').strip()

    try:
        page = max(1, int(page_raw))
    except (TypeError, ValueError):
        page = 1

    offset = (page - 1) * ITEMS_PER_PAGE

    if query:
        if sc.is_valid_url(query):
            track_info = await sc.async_get_track_metadata(query)
            results = [track_info] if track_info else []
        else:
            results = await sc.async_search_tracks(
                query,
                limit=ITEMS_PER_PAGE + 1,
                offset=offset,
                source=source,
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
        source=source,
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
    as_video  = form.get('as_video') == 'true'
    user      = current_user()
    file_path, _ = await sc.async_download_track(url, as_video=as_video)
    await DB.add_to_history(user['id'], title, url)
    
    ext = os.path.splitext(file_path)[1].lstrip('.') or ('mp4' if as_video else 'mp3')
    
    return await send_file(
        file_path,
        as_attachment=True,
        attachment_filename=f"{title}.{ext}",
    )


# ─── МастерШеф ─────────────────────────────────────────────────────────────────

@app.route('/masterchef/search')
@login_required
async def masterchef_search():
    query = request.args.get('q', '').strip()
    try:
        episodes = await stb.async_search_episodes(query=query, limit=30)
    except Exception as e:
        episodes = []
    return jsonify({'episodes': episodes})


@app.route('/masterchef/download', methods=['GET', 'POST'])
@login_required
async def masterchef_download():
    """
    Асинхронний проксі-стрімінг файлу з CDN до браузера користувача.
    - Оскільки завантаження йде частинами через локальний сервер (localhost),
      швидкість передачі до браузера миттєва, а швидкість скачування з CDN максимальна.
    - Використовує Content-Disposition: attachment, що змушує браузер саме
      скачувати файл на диск, а не намагатись відтворити його.
    - Підтримує методи POST та GET, оскільки деякі браузери роблять запити GET
      для перевірки заголовків, дозавантаження або при повторних спробах.
    """
    if request.method == 'POST':
        form    = await request.form
        stb_url = form.get('url', '')
    else:
        stb_url = request.args.get('url', '')

    user = current_user()

    if not stb_url or not stb.is_stb_url(stb_url):
        return "Невірне посилання STB", 400

    try:
        info = await stb.async_get_episode_info(stb_url)
    except RuntimeError as e:
        return f"Помилка: {e}", 400

    title = info['title']
    await DB.add_to_history(user['id'], title, stb_url)

    safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
    filename = f"{safe_title}.mp4"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Referer': 'https://player.starlight.digital/',
        'Origin': 'https://player.starlight.digital',
    }

    # Отримуємо точний розмір файлу через HEAD-запит для показу прогресу в браузері
    import httpx
    content_length = None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            head_resp = await client.head(info['url'], headers=headers)
            content_length = head_resp.headers.get('content-length')
    except Exception as e:
        print(f"[masterchef_download] Не вдалося отримати Content-Length: {e}")

    async def generate():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", info['url'], headers=headers) as r:
                    r.raise_for_status()
                    async for chunk in r.aiter_bytes(chunk_size=256 * 1024):  # Блоки по 256 KB
                        yield chunk
        except asyncio.CancelledError:
            print("[masterchef_download] Завантаження перервано/скасовано користувачем.")
            raise
        except Exception as e:
            print(f"[masterchef_download] Помилка стрімінгу: {e}")
            raise

    quoted_filename = urllib.parse.quote(filename)
    response_headers = {
        'Content-Disposition': f"attachment; filename*=UTF-8''{quoted_filename}",
        'Content-Type': 'video/mp4',
    }
    if content_length:
        response_headers['Content-Length'] = content_length

    return Response(generate(), headers=response_headers)


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