import telebot
from telebot import types
import soundcloud_service as sc
import os

search_results = {}

def register_handlers(bot_obj):
    @bot_obj.message_handler(commands=['start'])
    def start(message):
        bot_obj.send_message(message.chat.id, "🎧 Привіт! Скинь назву треку або пряме посилання на SoundCloud.")

    @bot_obj.message_handler(func=lambda m: True)
    def handle_all(message):
        query = message.text
        # Перевірка на посилання
        if "soundcloud.com/" in query:
            status = bot_obj.send_message(message.chat.id, "📥 Обробляю посилання...")
            try:
                file_path = sc.download_track(query)
                with open(file_path, 'rb') as audio:
                    bot_obj.send_audio(message.chat.id, audio)
                os.remove(file_path)
                bot_obj.delete_message(message.chat.id, status.message_id)
            except Exception as e:
                bot_obj.edit_message_text(f"❌ Помилка: {e}", message.chat.id, status.message_id)
        else:
            # Звичайний пошук
            results = sc.search_tracks(query, limit=5)
            if not results:
                bot_obj.send_message(message.chat.id, "Нічого не знайдено.")
                return
            search_results[message.chat.id] = results
            markup = types.InlineKeyboardMarkup()
            for idx, t in enumerate(results):
                markup.add(types.InlineKeyboardButton(f"🎵 {t['title'][:35]}", callback_data=f"dl_{idx}"))
            bot_obj.send_message(message.chat.id, "Оберіть трек:", reply_markup=markup)

    @bot_obj.callback_query_handler(func=lambda call: call.data.startswith('dl_'))
    def callback_download(call):
        chat_id = call.message.chat.id
        idx = int(call.data.split('_')[1])
        track = search_results.get(chat_id, [])[idx]
        bot_obj.answer_callback_query(call.id, "Завантаження...")
        try:
            file_path = sc.download_track(track['url'])
            with open(file_path, 'rb') as audio:
                bot_obj.send_audio(chat_id, audio, title=track['title'], performer=track['uploader'])
            if os.path.exists(file_path): os.remove(file_path)
        except Exception as e:
            bot_obj.send_message(chat_id, f"Помилка: {e}")