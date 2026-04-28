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


async def get_user_history(user_id: int, limit: int = 20) -> list[dict]:
    """Історія конкретного користувача."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            '''SELECT track_title, track_url, download_date
               FROM history WHERE user_id = ?
               ORDER BY download_date DESC LIMIT ?''',
            (user_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_recent_history(limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            '''SELECT track_title, download_date FROM history
               ORDER BY download_date DESC LIMIT ?''',
            (limit,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_stats() -> tuple[int, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM users') as cur:
            (total_users,) = await cur.fetchone()
        async with db.execute('SELECT COUNT(*) FROM history') as cur:
            (total_downloads,) = await cur.fetchone()
    return total_users, total_downloads


async def admin_get_all_downloads(limit: int = 300) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            '''SELECT h.id, h.track_title, h.track_url, h.download_date,
                      COALESCE(u.username, u.first_name, 'Web') as display_name,
                      h.user_id
               FROM history h
               LEFT JOIN users u ON h.user_id = u.user_id
               ORDER BY h.download_date DESC LIMIT ?''',
            (limit,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def admin_get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            '''SELECT u.user_id, u.username, u.first_name, u.join_date,
                      COUNT(h.id) as downloads
               FROM users u
               LEFT JOIN history h ON u.user_id = h.user_id
               GROUP BY u.user_id
               ORDER BY downloads DESC''',
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def admin_delete_history_record(record_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM history WHERE id = ?', (record_id,))
        await db.commit()


async def admin_get_downloads_by_day(days: int = 30) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            '''SELECT DATE(download_date) as day, COUNT(*) as count
               FROM history
               WHERE download_date >= DATE('now', ? || ' days')
               GROUP BY day ORDER BY day''',
            (f'-{days}',),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def admin_get_top_tracks(limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            '''SELECT track_title, COUNT(*) as count
               FROM history GROUP BY track_title
               ORDER BY count DESC LIMIT ?''',
            (limit,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def admin_get_new_users_by_day(days: int = 30) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            '''SELECT DATE(join_date) as day, COUNT(*) as count
               FROM users
               WHERE join_date >= DATE('now', ? || ' days')
               GROUP BY day ORDER BY day''',
            (f'-{days}',),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]