import os
import asyncio
from collections import OrderedDict

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

import soundcloud_service as sc
import DB

router = Router()

ITEMS_PER_PAGE = 5
ADMIN_IDS: list[int] = [
    int(x) for x in os.getenv('ADMIN_IDS', '1304231128,755351441').split(',') if x.strip()
]



class _LRUCache(OrderedDict):
    def __init__(self, maxsize: int = 200):
        super().__init__()
        self._maxsize = maxsize

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)
        if len(self) > self._maxsize:
            self.popitem(last=False)


search_results: _LRUCache = _LRUCache(maxsize=200)
playlist_cache: _LRUCache = _LRUCache(maxsize=200)
track_cache: _LRUCache = _LRUCache(maxsize=200)


# Меню та клавіатури

def get_main_menu_markup() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🎵 Музика", callback_data="menu_music"),
        types.InlineKeyboardButton(text="🎬 YouTube", callback_data="menu_youtube")
    )
    builder.row(
        types.InlineKeyboardButton(text="📺 СТБ", callback_data="menu_stb")
    )
    return builder.as_markup()


def get_back_markup() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="⬅️ Назад до меню", callback_data="menu_back")
    )
    return builder.as_markup()


# Команди

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await DB.add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    await message.answer(
        "👋 *Привіт!* Я універсальний завантажувач медіа.\n\n"
        "Оберіть розділ меню нижче, щоб розпочати:",
        reply_markup=get_main_menu_markup(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "menu_back")
async def cb_menu_back(call: types.CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "👋 *Привіт!* Я універсальний завантажувач медіа.\n\n"
        "Оберіть розділ меню нижче, щоб розпочати:",
        reply_markup=get_main_menu_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "menu_music")
async def cb_menu_music(call: types.CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "🎵 *Музика (SoundCloud)*\n\n"
        "Надішліть мені **назву пісні** для пошуку або **пряме посилання** на трек/плейлист із SoundCloud.",
        reply_markup=get_back_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "menu_youtube")
async def cb_menu_youtube(call: types.CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "🎬 *YouTube завантажувач*\n\n"
        "Надішліть мені **пряме посилання** на відео, Shorts або YouTube Music.\n\n"
        "💡 *Корисна порада:* також ви можете шукати відео на YouTube прямо в чаті! Для цього почніть запит з `yt: ` (наприклад: `yt: Queen Bohemian Rhapsody`).",
        reply_markup=get_back_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "menu_stb")
async def cb_menu_stb(call: types.CallbackQuery):
    await call.answer()
    web_url = os.getenv('WEB_URL', '')
    url_text = f"\n\n🌐 [Перейти до веб-сайту]({web_url})" if web_url else ""
    await call.message.edit_text(
        "📺 *МастерШеф (СТБ)*\n\n"
        "⚠️ Завантаження та перегляд серій СТБ через Telegram-бота недоступні.\n\n"
        "Ця функція працює **тільки через наш веб-сервіс** за умови використання пристрою з українським інтернет-провайдером (через регіональні обмеження СТБ та захист Cloudflare)."
        f"{url_text}",
        reply_markup=get_back_markup(),
        parse_mode="Markdown"
    )



@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ Ця команда доступна тільки адміністраторам.")
    users_count, downloads_count = await DB.get_stats()
    await message.answer(
        f"📊 *Статистика бота:*\n\n"
        f"👥 Користувачів: {users_count}\n"
        f"🎵 Завантажень: {downloads_count}",
        parse_mode="Markdown",
    )


# Пошук та пагінація

def _build_results_markup(results: list[dict], query: str, offset: int) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for idx, track in enumerate(results):
        title = track['title'][:40]
        builder.row(
            types.InlineKeyboardButton(text=f"🎵 {title}", callback_data=f"dl_{idx}")
        )

    nav: list[types.InlineKeyboardButton] = []
    if offset > 0:
        nav.append(types.InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"page_{query}_{offset - ITEMS_PER_PAGE}",
        ))
    if len(results) >= ITEMS_PER_PAGE:
        nav.append(types.InlineKeyboardButton(
            text="Далі ➡️",
            callback_data=f"page_{query}_{offset + ITEMS_PER_PAGE}",
        ))
    if nav:
        builder.row(*nav)

    return builder.as_markup()


async def send_search_results(
    target: types.Message | types.CallbackQuery,
    query: str,
    offset: int,
):
    results = await sc.async_search_tracks(query, limit=ITEMS_PER_PAGE, offset=offset)

    if not results:
        if isinstance(target, types.CallbackQuery):
            return await target.answer("Це остання сторінка.", show_alert=True)
        return await target.answer("🤷 Нічого не знайдено.")

    user_id = target.from_user.id
    search_results[user_id] = results

    markup = _build_results_markup(results, query, offset)
    text = (
        f"🔍 Результати для: `{query}`\n"
        f"📄 Сторінка: {offset // ITEMS_PER_PAGE + 1}"
    )

    try:
        if isinstance(target, types.Message):
            await target.answer(text, reply_markup=markup, parse_mode="Markdown")
        else:
            await target.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"[send_search_results] помилка: {e}")


@router.message(F.text.regexp(r'^[^/].*'))
async def handle_text(message: types.Message):
    clean_text = message.text.strip()
    
    # Intercept STB/Starlight URLs in the Telegram Bot
    if 'stb.ua' in clean_text.lower() or 'starlight.digital' in clean_text.lower():
        web_url = os.getenv('WEB_URL', '')
        url_text = f"\n\n🌐 [Перейти до веб-сайту]({web_url})" if web_url else ""
        return await message.answer(
            "📺 *МастерШеф (СТБ)*\n\n"
            "⚠️ Завантаження та перегляд серій СТБ через Telegram-бота недоступні.\n\n"
            "Ця функція працює **тільки через наш веб-сервіс** за умови використання пристрою з українським інтернет-провайдером (через регіональні обмеження СТБ та захист Cloudflare)."
            f"{url_text}",
            parse_mode="Markdown"
        )

    if sc.is_valid_url(clean_text):
        status = await message.answer("🔍 Аналізую посилання...")
        info = await sc.async_get_url_info(clean_text)
        await status.delete()
        
        if not info:
            return await message.answer("❌ Не вдалося отримати інформацію за цим посиланням.")
            
        if info['type'] == 'track':
            url_lower = clean_text.lower()
            if "youtube.com" in url_lower or "youtu.be" in url_lower or "music.youtube.com" in url_lower:
                return await _prompt_youtube_format(message, info)
            return await _download_track_direct(message, info)
        elif info['type'] == 'playlist':
            return await _handle_playlist_input(message, info)
            
    await send_search_results(message, clean_text, offset=0)


@router.callback_query(F.data.startswith("page_"))
async def cb_pagination(call: types.CallbackQuery):
    parts = call.data.split("_")
    offset = int(parts[-1])
    query = "_".join(parts[1:-1])
    await call.answer()
    await send_search_results(call, query, offset)


# Завантаження

async def _safe_edit(msg: types.Message, text: str):
    """Редагує повідомлення, ігноруючи помилку 'message not modified'."""
    try:
        await msg.edit_text(text, parse_mode="Markdown")
    except Exception:
        pass


async def _download_track_direct(message: types.Message, track: dict):
    status = await message.answer(f"📥 Завантажую трек: *{track['title']}*...", parse_mode="Markdown")
    file_path: str | None = None
    user_id = message.from_user.id

    async def on_progress(text: str):
        await _safe_edit(status, text)

    try:
        file_path, title = await sc.async_download_track(track['url'], progress_callback=on_progress)
        await message.answer_audio(
            types.FSInputFile(file_path),
            title=title,
            caption=f"✅ {title}",
        )
        await DB.add_to_history(user_id, title, track['url'])
        await status.delete()
    except Exception as e:
        if str(e) == "DRM_PROTECTED":
            await _safe_edit(status, f"❌ Помилка: Трек *{track['title']}* захищений DRM і не може бути завантажений.", parse_mode="Markdown")
        else:
            await _safe_edit(status, f"❌ Помилка завантаження: {e}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


async def _handle_playlist_input(message: types.Message, playlist: dict):
    playlist_id = playlist['id']
    playlist_cache[playlist_id] = playlist
    
    tracks = playlist['tracks']
    total_tracks = len(tracks)
    
    tracks_list_str = ""
    for t in tracks[:10]:
        tracks_list_str += f"• {t['title']}\n"
    if total_tracks > 10:
        tracks_list_str += f"• та ще {total_tracks - 10} треків...\n"
        
    text = (
        f"📋 *Плейлист:* {playlist['title']}\n"
        f"👥 *Виконавець/Канал:* {tracks[0]['uploader'] if tracks else 'Невідомо'}\n"
        f"🎵 *Всього треків:* {total_tracks}\n\n"
        f"📝 *Список треків:*\n{tracks_list_str}\n"
        f"Оберіть варіант завантаження:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📥 Завантажити все", callback_data=f"pl_all_{playlist_id}")
    )
    builder.row(
        types.InlineKeyboardButton(text="📂 Вибірково", callback_data=f"pl_sel_{playlist_id}_0")
    )
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("dl_"))
async def cb_download(call: types.CallbackQuery):
    user_id = call.from_user.id
    idx = int(call.data.split("_")[1])
    tracks = search_results.get(user_id)
    file_path: str | None = None

    if not tracks or idx >= len(tracks):
        return await call.answer(
            "Результати застаріли, спробуйте пошук знову.",
            show_alert=True,
        )

    track = tracks[idx]
    
    url_lower = track['url'].lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower or "music.youtube.com" in url_lower:
        await call.answer()
        return await _prompt_youtube_format(call.message, track)

    await call.answer()

    status = await call.message.answer(
        f"📥 Готую до завантаження: *{track['title']}*",
        parse_mode="Markdown",
    )

    async def on_progress(text: str):
        await _safe_edit(status, text)

    try:
        file_path, _ = await sc.async_download_track(
            track['url'],
            progress_callback=on_progress,
        )
        await call.message.answer_audio(
            types.FSInputFile(file_path),
            title=track['title'],
            caption=f"✅ {track['title']}",
        )
        await DB.add_to_history(user_id, track['title'], track['url'])
        await status.delete()
    except Exception as e:
        if str(e) == "DRM_PROTECTED":
            await _safe_edit(status, f"❌ Помилка: Трек *{track['title']}* захищений DRM і не може бути завантажений.", parse_mode="Markdown")
        else:
            await _safe_edit(status, f"❌ Помилка: {e}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


@router.callback_query(F.data.startswith("pl_all_"))
async def cb_playlist_all(call: types.CallbackQuery):
    playlist_id = call.data.split("_")[2]
    playlist = playlist_cache.get(playlist_id)
    
    if not playlist:
        return await call.answer("Результати застаріли, спробуйте ще раз.", show_alert=True)
        
    await call.answer()
    user_id = call.from_user.id
    tracks = playlist['tracks']
    total = len(tracks)
    
    status = await call.message.answer(
        f"🚀 *Починаю завантаження плейлиста:* {playlist['title']} (0/{total})...",
        parse_mode="Markdown"
    )
    
    downloaded_count = 0
    skipped_count = 0
    
    for idx, track in enumerate(tracks):
        await _safe_edit(
            status, 
            f"📥 *Завантаження плейлиста:* {downloaded_count + skipped_count}/{total} треків оброблено...\n"
            f"Поточний трек: *{track['title']}*"
        )
        
        file_path = None
        
        async def on_progress(text: str):
            await _safe_edit(
                status,
                f"📥 *Завантаження плейлиста:* {downloaded_count + skipped_count}/{total} треків оброблено...\n"
                f"Поточний трек: *{track['title']}*\n"
                f"{text}"
            )
            
        try:
            file_path, title = await sc.async_download_track(track['url'], progress_callback=on_progress)
            await call.message.answer_audio(
                types.FSInputFile(file_path),
                title=title,
                caption=f"✅ {title} ({idx+1}/{total})",
            )
            await DB.add_to_history(user_id, title, track['url'])
            downloaded_count += 1
        except Exception as e:
            skipped_count += 1
            if str(e) == "DRM_PROTECTED":
                await call.message.answer(
                    f"⚠️ Трек *{track['title']}* пропущено (захищений DRM).",
                    parse_mode="Markdown"
                )
            else:
                await call.message.answer(
                    f"❌ Трек *{track['title']}* пропущено через помилку: {e}",
                    parse_mode="Markdown"
                )
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                
    await _safe_edit(
        status, 
        f"✅ *Завантаження завершено!*\n"
        f"Успішно завантажено: {downloaded_count}\n"
        f"Пропущено: {skipped_count}"
    )


@router.callback_query(F.data.startswith("pl_sel_"))
async def cb_playlist_selective(call: types.CallbackQuery):
    parts = call.data.split("_")
    playlist_id = parts[2]
    offset = int(parts[3])
    
    playlist = playlist_cache.get(playlist_id)
    if not playlist:
        return await call.answer("Результати застаріли, спробуйте ще раз.", show_alert=True)
        
    await call.answer()
    tracks = playlist['tracks']
    total = len(tracks)
    
    page_tracks = tracks[offset: offset + ITEMS_PER_PAGE]
    
    text = (
        f"📂 *Вибір треків з плейлиста:*\n"
        f"📄 Сторінка: {offset // ITEMS_PER_PAGE + 1} / {(total - 1) // ITEMS_PER_PAGE + 1}\n"
        f"Оберіть трек для завантаження:"
    )
    
    builder = InlineKeyboardBuilder()
    for t in page_tracks:
        title = t['title'][:40]
        builder.row(
            types.InlineKeyboardButton(
                text=f"🎵 {title}",
                callback_data=f"pl_dl_{playlist_id}_{t['index']}"
            )
        )
        
    nav: list[types.InlineKeyboardButton] = []
    if offset > 0:
        nav.append(types.InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"pl_sel_{playlist_id}_{offset - ITEMS_PER_PAGE}"
        ))
    nav.append(types.InlineKeyboardButton(
        text="📋 Меню плейлиста",
        callback_data=f"pl_menu_{playlist_id}"
    ))
    if offset + ITEMS_PER_PAGE < total:
        nav.append(types.InlineKeyboardButton(
            text="Далі ➡️",
            callback_data=f"pl_sel_{playlist_id}_{offset + ITEMS_PER_PAGE}"
        ))
        
    builder.row(*nav)
    
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("pl_menu_"))
async def cb_playlist_menu(call: types.CallbackQuery):
    playlist_id = call.data.split("_")[2]
    playlist = playlist_cache.get(playlist_id)
    if not playlist:
        return await call.answer("Результати застаріли, спробуйте ще раз.", show_alert=True)
        
    await call.answer()
    tracks = playlist['tracks']
    total_tracks = len(tracks)
    
    tracks_list_str = ""
    for t in tracks[:10]:
        tracks_list_str += f"• {t['title']}\n"
    if total_tracks > 10:
        tracks_list_str += f"• та ще {total_tracks - 10} треків...\n"
        
    text = (
        f"📋 *Плейлист:* {playlist['title']}\n"
        f"👥 *Виконавець/Канал:* {tracks[0]['uploader'] if tracks else 'Невідомо'}\n"
        f"🎵 *Всього треків:* {total_tracks}\n\n"
        f"📝 *Список треків:*\n{tracks_list_str}\n"
        f"Оберіть варіант завантаження:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📥 Завантажити все", callback_data=f"pl_all_{playlist_id}")
    )
    builder.row(
        types.InlineKeyboardButton(text="📂 Вибірково", callback_data=f"pl_sel_{playlist_id}_0")
    )
    
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("pl_dl_"))
async def cb_playlist_download_track(call: types.CallbackQuery):
    parts = call.data.split("_")
    playlist_id = parts[2]
    track_idx = int(parts[3])
    
    playlist = playlist_cache.get(playlist_id)
    if not playlist or track_idx >= len(playlist['tracks']):
        return await call.answer("Результати застаріли, спробуйте ще раз.", show_alert=True)
        
    await call.answer()
    track = playlist['tracks'][track_idx]
    user_id = call.from_user.id
    
    status = await call.message.answer(
        f"📥 Готую до завантаження: *{track['title']}*",
        parse_mode="Markdown",
    )
    
    async def on_progress(text: str):
        await _safe_edit(status, text)
        
    file_path = None
    try:
        file_path, title = await sc.async_download_track(track['url'], progress_callback=on_progress)
        await call.message.answer_audio(
            types.FSInputFile(file_path),
            title=title,
            caption=f"✅ {title}",
        )
        await DB.add_to_history(user_id, title, track['url'])
        await status.delete()
    except Exception as e:
        if str(e) == "DRM_PROTECTED":
            await _safe_edit(status, f"❌ Помилка: Трек *{track['title']}* захищений DRM і не може бути завантажений.", parse_mode="Markdown")
        else:
            await _safe_edit(status, f"❌ Помилка: {e}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


async def _prompt_youtube_format(message: types.Message, track: dict):
    track_id = track.get('id') or str(hash(track['url']))
    track_cache[track_id] = track
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🎵 MP3 (Аудіо)", callback_data=f"yt_dl_mp3_{track_id}"),
        types.InlineKeyboardButton(text="🎬 MP4 (Відео)", callback_data=f"yt_dl_mp4_{track_id}")
    )
    
    await message.answer(
        f"🎬 *Знайдено відео:* {track['title']}\n"
        f"Оберіть формат для завантаження:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("yt_dl_"))
async def cb_yt_download(call: types.CallbackQuery):
    parts = call.data.split("_")
    fmt = parts[2]
    track_id = "_".join(parts[3:])
    
    track = track_cache.get(track_id)
    if not track:
        return await call.answer("Результати застаріли, надішліть посилання знову.", show_alert=True)
        
    await call.answer()
    as_video = fmt == "mp4"
    user_id = call.from_user.id
    
    status = await call.message.answer(
        f"📥 Готую до завантаження ({fmt.upper()}): *{track['title']}*",
        parse_mode="Markdown",
    )
    
    async def on_progress(text: str):
        await _safe_edit(status, text)
        
    file_path = None
    try:
        file_path, title = await sc.async_download_track(
            track['url'],
            progress_callback=on_progress,
            as_video=as_video,
        )
        
        file_size = os.path.getsize(file_path)
        if file_size > 50 * 1024 * 1024:
            await _safe_edit(status, f"⚠️ Файл занадто великий для відправки через Telegram (більше 50 MB).\nБудь ласка, завантажте його через веб-сайт.")
            return
            
        if as_video:
            await call.message.answer_video(
                types.FSInputFile(file_path),
                caption=f"✅ {title}",
            )
        else:
            await call.message.answer_audio(
                types.FSInputFile(file_path),
                title=title,
                caption=f"✅ {title}",
            )
        await DB.add_to_history(user_id, title, track['url'])
        await status.delete()
    except Exception as e:
        if str(e) == "DRM_PROTECTED":
            await _safe_edit(status, f"❌ Помилка: Трек *{track['title']}* захищений DRM і не може бути завантажений.", parse_mode="Markdown")
        else:
            await _safe_edit(status, f"❌ Помилка: {e}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)