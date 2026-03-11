import telebot
from telebot import types
import soundcloud_service as sc

def register_handlers(bot):
    @bot.message_handler(commands=['start'])
    def start(message):
        bot.send_message(message.chat.id, "🎧 Привіт! Напиши назву треку.")

    @bot.message_handler(func=lambda m: True)
    def handle_search(message):
        results = sc.search_tracks(message.text, limit=5)
        if not results:
            bot.send_message(message.chat.id, "Нічого не знайдено.")
            return

        markup = types.InlineKeyboardMarkup()
        for idx, t in enumerate(results):
            callback_data = f"dl_{idx}" 
            markup.add(types.InlineKeyboardButton(f"🎵 {t['title']}", callback_data=callback_data))
        
        bot.send_message(message.chat.id, "Оберіть трек:", reply_markup=markup)
