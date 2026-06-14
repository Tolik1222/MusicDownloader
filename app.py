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


@app.before_serving
async def run_startup_diagnostics():
    print("🕵️‍♂️ Запуск діагностики з'єднання з STB...")
    import urllib.request
    import httpx
    url = "https://www.stb.ua/masterchef/ua/video-2/"
    
    headers_basic = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept-Language': 'uk,ru;q=0.9,en;q=0.8',
    }
    
    headers_full = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'uk-UA,uk;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    }
    
    try:
        req = urllib.request.Request(url, headers=headers_basic)
        loop = asyncio.get_running_loop()
        def _test_urllib(r):
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, len(resp.read())
        status, length = await loop.run_in_executor(None, _test_urllib, req)
        print(f"  [DIAG] urllib basic: УСПІХ (Status: {status}, {length} bytes)")
    except Exception as e:
        print(f"  [DIAG] urllib basic: ПОМИЛКА ({e})")
        
    try:
        req = urllib.request.Request(url, headers=headers_full)
        loop = asyncio.get_running_loop()
        def _test_urllib_full(r):
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, len(resp.read())
        status, length = await loop.run_in_executor(None, _test_urllib_full, req)
        print(f"  [DIAG] urllib full: УСПІХ (Status: {status}, {length} bytes)")
    except Exception as e:
        print(f"  [DIAG] urllib full: ПОМИЛКА ({e})")
        
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers_basic)
            print(f"  [DIAG] httpx basic: УСПІХ (Status: {resp.status_code}, {len(resp.content)} bytes)")
    except Exception as e:
        print(f"  [DIAG] httpx basic: ПОМИЛКА ({e})")
        
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers_full)
            print(f"  [DIAG] httpx full: УСПІХ (Status: {resp.status_code}, {len(resp.content)} bytes)")
    except Exception as e:
        print(f"  [DIAG] httpx full: ПОМИЛКА ({e})")

    # CDN test
    try:
        cdn_url = "https://e3p.starlight.digital/"
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            resp = await client.get(cdn_url)
            print(f"  [DIAG] CDN connection: УСПІХ (Status: {resp.status_code})")
    except Exception as e:
        print(f"  [DIAG] CDN connection: ПОМИЛКА ({e})")


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
        # Якщо введено пряме посилання на серію з сайту stb.ua
        if stb.is_stb_url(query):
            info = await stb.async_get_episode_info(query)
            episodes = [{
                'title': info['title'],
                'url': query,
                'poster': info.get('poster', '')
            }]
        else:
            episodes = await stb.async_search_episodes(query=query, limit=30)
    except Exception as e:
        print(f"[masterchef_search] Помилка пошуку або парсингу серії з STB: {e}")
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

    if content_length:
        file_size = int(content_length)
        CHUNK_SIZE = 2 * 1024 * 1024  # 2 MB chunks
        CONCURRENT_REQUESTS = 8        # 8 паралельних підключень
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

        async def generate():
            async def download_chunk(client, chunk_index):
                start = chunk_index * CHUNK_SIZE
                end = min(start + CHUNK_SIZE - 1, file_size - 1)
                for attempt in range(3):
                    try:
                        chunk_headers = dict(headers)
                        chunk_headers['Range'] = f"bytes={start}-{end}"
                        resp = await client.get(info['url'], headers=chunk_headers)
                        resp.raise_for_status()
                        return chunk_index, resp.content
                    except Exception as e:
                        if attempt == 2:
                            raise e
                        await asyncio.sleep(0.5)

            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    tasks = {}
                    # Запускаємо завантаження перших W частин паралельно
                    for idx in range(min(CONCURRENT_REQUESTS, total_chunks)):
                        tasks[idx] = asyncio.create_task(download_chunk(client, idx))

                    for idx in range(total_chunks):
                        # Чекаємо черговий шматок і одразу ж передаємо його клієнту
                        _, data = await tasks[idx]
                        yield data
                        del tasks[idx]

                        # Стартуємо завантаження наступного по черзі шматка
                        next_idx = idx + CONCURRENT_REQUESTS
                        if next_idx < total_chunks:
                            tasks[next_idx] = asyncio.create_task(download_chunk(client, next_idx))
            except asyncio.CancelledError:
                print("[masterchef_download] Завантаження перервано/скасовано користувачем.")
                raise
            except Exception as e:
                print(f"[masterchef_download] Помилка паралельного стрімінгу: {e}")
                raise
    else:
        # Fallback на звичайний послідовний стрімінг, якщо не вдалося отримати розмір
        async def generate():
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("GET", info['url'], headers=headers) as r:
                        r.raise_for_status()
                        async for chunk in r.aiter_bytes(chunk_size=256 * 1024):
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