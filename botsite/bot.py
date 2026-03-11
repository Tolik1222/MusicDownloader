import telebot
from telebot import types
import soundcloud_service as sc

def register_handlers(bot_obj):
    @bot_obj.message_handler(commands=['start'])
    def start(message):
        bot_obj.reply_to(message, "🎧 Привіт! Я ваш SoundCloud бот.\nНапиши назву пісні для пошуку.")

    @bot_obj.message_handler(func=lambda m: True)
    def handle_search(message):
        query = message.text
        status = bot_obj.send_message(message.chat.id, "🔍 Шукаю...")
        results = sc.search_tracks(query, limit=5)
        
        if not results:
            bot_obj.edit_message_text("Нічого не знайдено.", message.chat.id, status.message_id)
            return

        markup = types.InlineKeyboardMarkup()
        for idx, track in enumerate(results):
            markup.add(types.InlineKeyboardButton(f"🎵 {track['title'][:30]}", callback_data=f"info_{idx}"))
        
        bot_obj.edit_message_text("Оберіть трек:", message.chat.id, status.message_id, reply_markup=markup)

    @bot_obj.callback_query_handler(func=lambda call: call.data.startswith('info_'))
    def callback_info(call):
        bot_obj.answer_callback_query(call.id, "Функція завантаження в розробці...")
