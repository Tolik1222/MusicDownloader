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


# Простий LRU-кеш для результатів пошуку

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


# Команди

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await DB.add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    await message.answer(
        "🎧 *Привіт!* Скинь назву треку або посилання на SoundCloud.",
        parse_mode="Markdown",
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
    if "soundcloud.com/" in message.text:
        return await _download_by_link(message, message.text.strip())
    await send_search_results(message, message.text.strip(), offset=0)


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


async def _download_by_link(message: types.Message, url: str):
    status = await message.answer("📥 Завантажую трек за посиланням...")
    file_path: str | None = None

    async def on_progress(text: str):
        await _safe_edit(status, text)

    try:
        file_path = await sc.async_download_track(url, progress_callback=on_progress)
        await message.answer_audio(types.FSInputFile(file_path))
        await status.delete()
    except Exception as e:
        await _safe_edit(status, f"❌ Помилка завантаження: {e}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


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
    await call.answer()

    status = await call.message.answer(
        f"📥 Готую до завантаження: *{track['title']}*",
        parse_mode="Markdown",
    )

    async def on_progress(text: str):
        await _safe_edit(status, text)

    try:
        file_path = await sc.async_download_track(
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
        await _safe_edit(status, f"❌ Помилка: {e}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)