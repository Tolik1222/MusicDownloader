import telebot
import os
import requests
import time
from .downloader_yt import get_yt_download_url # Змінили імпорт!

def init_bot(token):
    if not token:
        print("Telegram token is not set!")
        # Повертаємо пустишку, щоб сайт не падав, якщо токена немає
        return telebot.TeleBot("123:dummy") 

    bot = telebot.TeleBot(token)

    @bot.message_handler(commands=['start'])
    def welcome(message):
        bot.reply_to(message, "Привіт! Надішліть посилання на YouTube або SoundCloud, і я підготую файл. 🎵")

    @bot.message_handler(func=lambda m: True)
    def handle_link(message):
        url = message.text
        if "youtube.com" not in url and "youtu.be" not in url and "soundcloud.com" not in url:
            bot.reply_to(message, "Будь ласка, надішліть коректне посилання.")
            return

        msg = bot.send_message(message.chat.id, "⏳ Обробка запиту...")

        try:
            # Оскільки Cobalt підтримує і SC і YT, використовуємо одну функцію
            download_link = get_yt_download_url(url)
            if not download_link:
                bot.edit_message_text("❌ Не вдалося отримати файл.", message.chat.id, msg.message_id)
                return

            bot.edit_message_text("📥 Завантаження файлу...", message.chat.id, msg.message_id)
            audio_data = requests.get(download_link, timeout=60).content
            temp_filename = f"audio_{int(time.time())}.mp3"
            
            with open(temp_filename, "wb") as f:
                f.write(audio_data)

            with open(temp_filename, "rb") as audio:
                bot.send_audio(message.chat.id, audio, caption="✅ Готово!")
            
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
            bot.delete_message(message.chat.id, msg.message_id)

        except Exception as e:
            bot.edit_message_text(f"❌ Помилка: {str(e)}", message.chat.id, msg.message_id)

    return bot