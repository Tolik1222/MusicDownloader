import telebot
import os
import requests
import time
from .downloader import get_invidious_download_url

def init_bot(token):
    bot = telebot.TeleBot(token)

    @bot.message_handler(commands=['start'])
    def welcome(message):
        bot.reply_to(message, "Привіт! Надішліть посилання на SoundCloud або YouTube, і я підготую файл для вас. 🎵")

    @bot.message_handler(func=lambda m: True)
    def handle_link(message):
        url = message.text

        if not any(domain in url for domain in ["soundcloud.com", "youtube.com", "youtu.be"]):
            bot.reply_to(message, "Будь ласка, надішліть коректне посилання на SoundCloud або YouTube.")
            return

        msg = bot.send_message(message.chat.id, "⏳ Обробка посилання через Cobalt...")

        try:
            download_link = get_invidious_download_url(url
            
            if not download_link:
                bot.edit_message_text("❌ Не вдалося отримати файл. Спробуйте інше посилання.", 
                                     message.chat.id, msg.message_id)
                return

            audio_data = requests.get(download_link).content

            temp_filename = f"audio_{int(time.time())}.mp3"
            
            with open(temp_filename, "wb") as f:
                f.write(audio_data)

            with open(temp_filename, "rb") as audio:
                bot.send_audio(
                    message.chat.id, 
                    audio, 
                    caption="✅ Ваш файл готовий!"
                )

            if os.path.exists(temp_filename):
                os.remove(temp_filename)
            bot.delete_message(message.chat.id, msg.message_id)

        except Exception as e:
            bot.edit_message_text(f"❌ Помилка: {str(e)}", message.chat.id, msg.message_id)
            if 'temp_filename' in locals() and os.path.exists(temp_filename):
                os.remove(temp_filename)

    return bot