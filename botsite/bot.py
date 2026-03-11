import telebot
from telebot import types
import soundcloud_service as sc
import os

search_results = {}

def register_handlers(bot_obj):
    @bot_obj.message_handler(commands=['start'])
    def start(message):
        bot_obj.reply_to(message, "🎧 Привіт! Я ваш SoundCloud бот.\nНадішліть назву пісні або посилання.")

    @bot_obj.message_handler(func=lambda m: True)
    def handle_search(message):
        query = message.text
        status = bot_obj.send_message(message.chat.id, "🔍 Шукаю на SoundCloud...")
        
        results = sc.search_tracks(query, limit=5)
        
        if not results:
            bot_obj.edit_message_text("Нічого не знайдено 😔", message.chat.id, status.message_id)
            return

        search_results[message.chat.id] = results

        markup = types.InlineKeyboardMarkup()
        for idx, track in enumerate(results):
            markup.add(types.InlineKeyboardButton(f"🎵 {track['title'][:35]}...", callback_data=f"dl_{idx}"))
        
        bot_obj.edit_message_text("Оберіть трек для завантаження:", message.chat.id, status.message_id, reply_markup=markup)

    @bot_obj.callback_query_handler(func=lambda call: call.data.startswith('dl_'))
    def callback_download(call):
        chat_id = call.message.chat.id
        idx = int(call.data.split('_')[1])
        
        if chat_id not in search_results:
            bot_obj.answer_callback_query(call.id, "Пошук застарів. Спробуйте ще раз.", show_alert=True)
            return

        track = search_results[chat_id][idx]
        bot_obj.answer_callback_query(call.id, f"Починаю завантаження: {track['title'][:20]}...")
        
        status_msg = bot_obj.send_message(chat_id, "📥 Завантажую файл на сервер, почекайте...")

        try:
            file_path = sc.download_track(track['url'])
            
            with open(file_path, 'rb') as audio:
                bot_obj.send_audio(
                    chat_id, 
                    audio, 
                    title=track['title'], 
                    performer=track['uploader'],
                    duration=None 
            
            bot_obj.delete_message(chat_id, status_msg.message_id)
            if os.path.exists(file_path):
                os.remove(file_path)

        except Exception as e:
            bot_obj.edit_message_text(f"❌ Помилка завантаження: {e}", chat_id, status_msg.message_id)