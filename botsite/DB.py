import sqlite3
from datetime import datetime

DB_PATH = "bot_database.db"

async def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблиця користувачів
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            join_date DATETIME
        )
    ''')
    
    # Таблиця історії (з прив'язкою до user_id через FOREIGN KEY)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            track_title TEXT,
            track_url TEXT,
            download_date DATETIME,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

async def add_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Додаємо юзера, якщо його ще немає (IGNORE)
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, join_date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, datetime.now()))
    conn.commit()
    conn.close()

async def add_to_history(user_id, track_title, track_url):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO history (user_id, track_title, track_url, download_date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, track_title, track_url, datetime.now()))
    conn.commit()
    conn.close()

async def get_user_history(user_id, limit=10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT track_title, download_date 
        FROM history 
        WHERE user_id = ? 
        ORDER BY download_date DESC 
        LIMIT ?
    ''', (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows

async def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM history')
    total_downloads = cursor.fetchone()[0]
    conn.close()
    return total_users, total_downloads
