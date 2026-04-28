import aiosqlite
from datetime import datetime

DB_PATH = "bot_database.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")

        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                join_date  DATETIME
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER,
                track_title   TEXT,
                track_url     TEXT,
                download_date DATETIME,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        await db.commit()


async def add_user(user_id: int, username: str | None, first_name: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''INSERT OR IGNORE INTO users (user_id, username, first_name, join_date)
               VALUES (?, ?, ?, ?)''',
            (user_id, username, first_name, datetime.now()),
        )
        await db.commit()


async def add_to_history(user_id: int, track_title: str, track_url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''INSERT INTO history (user_id, track_title, track_url, download_date)
               VALUES (?, ?, ?, ?)''',
            (user_id, track_title, track_url, datetime.now()),
        )
        await db.commit()


async def get_user_history(user_id: int, limit: int = 10) -> list[tuple]:
    """Повертає останні `limit` завантажень конкретного користувача."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            '''SELECT track_title, download_date
               FROM history
               WHERE user_id = ?
               ORDER BY download_date DESC
               LIMIT ?''',
            (user_id, limit),
        ) as cursor:
            return await cursor.fetchall()


async def get_recent_history(limit: int = 10) -> list[tuple]:
    """Загальна історія для вебсайту (без прив'язки до user)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            '''SELECT track_title, download_date
               FROM history
               ORDER BY download_date DESC
               LIMIT ?''',
            (limit,),
        ) as cursor:
            return await cursor.fetchall()


async def get_stats() -> tuple[int, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM users') as cur:
            (total_users,) = await cur.fetchone()
        async with db.execute('SELECT COUNT(*) FROM history') as cur:
            (total_downloads,) = await cur.fetchone()
    return total_users, total_downloads