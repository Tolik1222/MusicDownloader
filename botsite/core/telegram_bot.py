import telebot
import os
import requests
import time
from .downloader import get_invidious_download_url

def init_bot(token):
    bot = telebot.TeleBot(token)

    @bot.message_handler(commands=['start'])
    def welcome(message):
        bot.reply_to(message, "Привіт! Надішліть посилання на YouTube, і я підготую файл через Invidious. 🎵")

    @bot.message_handler(func=lambda m: True)
    def handle_link(message):
        url = message.text
        if "youtube.com" not in url and "youtu.be" not in url:
            bot.reply_to(message, "Будь ласка, надішліть коректне посилання на YouTube.")
            return

        msg = bot.send_message(message.chat.id, "⏳ Отримання даних...")

        try:
            download_link = get_invidious_download_url(url)
            if not download_link:
                bot.edit_message_text("❌ Не вдалося отримати потік. Спробуйте інше відео.", message.chat.id, msg.message_id)
                return

            # Завантажуємо файл у пам'ять для відправки
            audio_data = requests.get(download_link, timeout=60).content
            temp_filename = f"audio_{int(time.time())}.mp3"
            
            with open(temp_filename, "wb") as f:
                f.write(audio_data)

            with open(temp_filename, "rb") as audio:
                bot.send_audio(message.chat.id, audio, caption="✅ Оброблено через проксі")
            
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
            bot.delete_message(message.chat.id, msg.message_id)

        except Exception as e:
            bot.edit_message_text(f"❌ Помилка: {str(e)}", message.chat.id, msg.message_id)

    return bot