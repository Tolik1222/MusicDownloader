import os
import asyncio
import shutil
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import soundcloud_service as sc
import DB 

router = Router()

# Тимчасове сховище результатів пошуку (user_id: [tracks])
search_results = {}

ITEMS_PER_PAGE = 5  
ADMIN_ID = [1304231128, 755351441]

# --- КОМАНДИ ---

@router.message(Command("stats"))
async def stats_command(message: types.Message):
    if message.from_user.id not in ADMIN_ID:
        return await message.answer("❌ Ця команда доступна тільки розробнику.")
    users_count, downloads_count = await DB.get_stats()
    await message.answer(f"📊 **Статистика бота:**\n\n👥 Користувачів: {users_count}\n🎵 Завантажень: {downloads_count}")

@router.message(Command("start"))
async def start_command(message: types.Message):
    await DB.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer("🎧 **Привіт!** Скинь назву треку або посилання на SoundCloud.")

# --- ПОШУК ТА ПАГІНАЦІЯ ---

async def send_search_results(message_or_call, query, offset):
    results = await sc.async_search_tracks(query, limit=ITEMS_PER_PAGE, offset=offset)
    
    if not results:
        if isinstance(message_or_call, types.CallbackQuery):
            return await message_or_call.answer("Це остання сторінка", show_alert=True)
        return await message_or_call.answer("🤷 Нічого не знайдено.")

    user_id = message_or_call.from_user.id
    search_results[user_id] = results 

    builder = InlineKeyboardBuilder()
    for idx, track in enumerate(results):
        builder.row(types.InlineKeyboardButton(text=f"🎵 {track['title'][:35]}", callback_data=f"dl_{idx}"))
    
    nav_btns = []
    if offset > 0:
        nav_btns.append(types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_{query}_{offset - ITEMS_PER_PAGE}"))
    
    if len(results) >= ITEMS_PER_PAGE:
        nav_btns.append(types.InlineKeyboardButton(text="Далі ➡️", callback_data=f"page_{query}_{offset + ITEMS_PER_PAGE}"))
    
    builder.row(*nav_btns)
    text = f"🔍 Результати для: `{query}`\n📄 Сторінка: {offset // ITEMS_PER_PAGE + 1}"

    try:
        if isinstance(message_or_call, types.Message):
            await message_or_call.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        else:
            await message_or_call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    except Exception as e:
        print(f"Помилка пагінації: {e}")

@router.message(F.text.regexp(r'^[^/].*'))
async def handle_text(message: types.Message):
    if "soundcloud.com/" in message.text:
        return await handle_link(message)
    await send_search_results(message, message.text, offset=0)

@router.callback_query(F.data.startswith("page_"))
async def callback_pagination(call: types.CallbackQuery):
    parts = call.data.split("_")
    offset = int(parts[-1])
    query = "_".join(parts[1:-1])
    await call.answer()
    await send_search_results(call, query, offset)

# --- ЗАВАНТАЖЕННЯ ---

async def handle_link(message: types.Message):
    url = message.text.strip()
    status_msg = await message.answer("📥 Завантажую трек за посиланням...")
    file_path = None

    async def progress_update(text):
        try: 
            await status_msg.edit_text(text, parse_mode="Markdown")
            await asyncio.sleep(0.5) # Захист від лімітів Telegram
        except: pass

    try:
        file_path = await sc.async_download_track(url, progress_callback=progress_update)
        await message.answer_audio(types.FSInputFile(file_path))
        await status_msg.delete()
    except Exception as e:
        if status_msg:
            await status_msg.edit_text(f"❌ Помилка завантаження: {e}")
    finally:
        # Гарантоване видалення файлу
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ Тимчасовий файл видалено: {file_path}")

@router.callback_query(F.data.startswith("dl_"))
async def callback_download(call: types.CallbackQuery):
    user_id = call.from_user.id
    idx = int(call.data.split("_")[1])
    tracks = search_results.get(user_id, [])
    file_path = None
    
    if not tracks:
        return await call.answer("Результати застаріли, спробуйте пошук знову.", show_alert=True)

    track = tracks[idx]
    await call.answer()
    status_msg = await call.message.answer(f"📥 Готую до завантаження: **{track['title']}**")

    async def progress_update(text):
        try: await status_msg.edit_text(text, parse_mode="Markdown")
        except: pass

    try:
        file_path = await sc.async_download_track(track['url'], progress_callback=progress_update)
        await call.message.answer_audio(
            types.FSInputFile(file_path), 
            title=track['title'],
            caption=f"✅ Готово: {track['title']}"
        )
        await DB.add_to_history(user_id, track['title'], track['url'])
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Помилка: {e}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ Тимчасовий файл видалено: {file_path}")