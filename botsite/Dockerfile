# Використовуємо офіційний образ Python
FROM python:3.13-slim

# Встановлюємо ffmpeg (він потрібен yt-dlp для перетворення музики в mp3)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Створюємо папку для бота всередині контейнера
WORKDIR /app

# Спочатку копіюємо список бібліотек
COPY requirements.txt .

# Встановлюємо бібліотеки
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо всі інші файли твого бота
COPY . .

# Команда, яка запустить твій бот
CMD ["python", "app.py"]