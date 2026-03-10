import telebot
import os
import requests
import time

def init_bot(token):
    if not token:
        return telebot.TeleBot("123:dummy") 

    bot = telebot.TeleBot(token)

    @bot.message_handler(commands=['start'])
    def welcome(message):
        bot.reply_to(message, "Привіт! Надішліть посилання на YouTube. 🎵")

    @bot.message_handler(func=lambda m: True)
    def handle_link(message):
        url = message.text
        if "youtube.com" not in url and "youtu.be" not in url:
            bot.reply_to(message, "Будь ласка, надішліть коректне посилання на YouTube.")
            return

        msg = bot.send_message(message.chat.id, "⏳ Обробка запиту через мобільне API...")

        try:
            from .downloader_yt import get_yt_download_url
            download_link, debug_info = get_yt_download_url(url)

            if not download_link:
                bot.edit_message_text(f"❌ Помилка:\n{debug_info[:200]}", message.chat.id, msg.message_id)
                return

            bot.edit_message_text("📥 Завантаження файлу на сервер...", message.chat.id, msg.message_id)
            
            # Завантажуємо трек
            audio_data = requests.get(download_link, timeout=60).content
            temp_filename = f"audio_{int(time.time())}.m4a"
            
            with open(temp_filename, "wb") as f:
                f.write(audio_data)

            with open(temp_filename, "rb") as audio:
                bot.send_audio(message.chat.id, audio, caption="✅ Завантажено успішно!")
            
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
            bot.delete_message(message.chat.id, msg.message_id)

        except Exception as e:
            bot.edit_message_text(f"❌ Системна помилка: {str(e)}", message.chat.id, msg.message_id)

    return bot