import telebot
import yt_dlp
import os
from .downloader import get_download_opts

def init_bot(token):
    bot = telebot.TeleBot(token)

    @bot.message_handler(commands=['start'])
    def welcome(message):
        bot.reply_to(message, "Привіт! Надішліть посилання на SoundCloud або YouTube, і я підготую файл для вас. 🎵")

    @bot.message_handler(func=lambda m: True)
    def handle_link(message):
        url = message.text
        if "soundcloud.com" not in url and "youtube.com" not in url and "youtu.be" not in url:
            bot.reply_to(message, "Будь ласка, надішліть коректне посилання.")
            return

        msg = bot.send_message(message.chat.id, "⏳ Обробка треку...")
        file_id = f"bot_{message.chat.id}_{int(os.path.getmtime('.'))}"
        output = os.path.join("downloads", file_id)

        try:
            opts = get_download_opts('mp3', output)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')

            with open(filename, 'rb') as audio:
                bot.send_audio(message.chat.id, audio, title=info.get('title'))
            
            os.remove(filename)
            bot.delete_message(message.chat.id, msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ Помилка: {str(e)}", message.chat.id, msg.message_id)

    return bot