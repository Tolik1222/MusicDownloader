"""
stb_service.py – сервіс для отримання прямих посилань на відео з сайту STB (stb.ua).

Принцип роботи:
  1. Завантажуємо HTML сторінки серії STB.
  2. Витягуємо hash гравця (player.starlight.digital).
  3. Робимо запит до Starlight API (vcms-api.starlight.digital) і отримуємо
     прямі MP4 посилання (якості mq / lq / hq).
  4. Повертаємо метадані та найкраще посилання для завантаження через yt-dlp або ffmpeg.
"""

import asyncio
import re
import urllib.request
import urllib.parse
import json
from typing import Optional


STARLIGHT_API = "https://vcms-api.starlight.digital/player-api/{hash}"
PLAYER_IFRAME_RE = re.compile(
    r'player\.starlight\.digital/vplayer/\?hash=([0-9a-f]{64})',
    re.IGNORECASE,
)

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'uk,ru;q=0.9,en;q=0.8',
}

QUALITY_PRIORITY = ('hq', 'mq', 'lq')


def is_stb_url(url: str) -> bool:
    """Перевіряє, чи є посилання з сайту STB."""
    return 'stb.ua' in url.lower()


def _fetch(url: str, extra_headers: dict | None = None) -> bytes:
    headers = dict(_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def _get_player_hash(stb_url: str) -> Optional[str]:
    """Парсить HTML сторінки STB і повертає hash гравця Starlight."""
    html = _fetch(stb_url).decode('utf-8', errors='replace')
    m = PLAYER_IFRAME_RE.search(html)
    return m.group(1) if m else None


def _call_starlight_api(player_hash: str, referer: str) -> dict:
    """Звертається до Starlight API і повертає розпарсений JSON."""
    api_url = (
        STARLIGHT_API.format(hash=player_hash)
        + f"?referer={urllib.parse.quote(referer)}&lang=ru"
    )
    raw = _fetch(
        api_url,
        extra_headers={
            'Referer': 'https://player.starlight.digital/',
            'Origin':  'https://player.starlight.digital',
        },
    )
    return json.loads(raw.decode('utf-8'))


def _pick_best_media(media_list: list) -> Optional[dict]:
    """Вибирає найкращу якість відео зі списку об'єктів {quality, url, ...}."""
    by_quality = {m.get('quality', ''): m for m in media_list}
    for q in QUALITY_PRIORITY:
        if q in by_quality:
            return by_quality[q]
    # якщо жодна пріоритетна якість не знайдена – беремо першу доступну
    return media_list[0] if media_list else None


OG_TITLE_RE = re.compile(r'<meta\s+property="og:title"\s+content="([^"]+)"', re.IGNORECASE)


def _get_page_title(stb_url: str) -> str:
    """Отримує заголовок серії з OG-мета тегу сторінки STB."""
    try:
        html = _fetch(stb_url).decode('utf-8', errors='replace')
        m = OG_TITLE_RE.search(html)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    # Fallback: генеруємо з URL-slug
    slug = stb_url.rstrip('/').split('/')[-1]
    return slug.replace('-', ' ').title()


def get_episode_info(stb_url: str) -> dict:
    """
    Синхронна функція. Повертає словник з інформацією про серію:
    {
        'title': str,
        'duration': int,          # секунди
        'poster': str,            # URL обкладинки
        'url': str,               # найкраще пряме MP4 посилання
        'quality': str,           # 'hq' / 'mq' / 'lq'
        'media': list[dict],      # всі доступні якості
    }
    Кидає RuntimeError якщо hash не знайдено або API повернув помилку.
    """
    player_hash = _get_player_hash(stb_url)
    if not player_hash:
        raise RuntimeError(
            "Не вдалося знайти гравець на сторінці. "
            "Переконайтесь, що це посилання на серію з stb.ua."
        )

    data = _call_starlight_api(player_hash, stb_url)

    # API може повернути type='video' або type='playlist'
    resp_type = data.get('type', '')
    if resp_type == 'video':
        video_obj = data['video'][0]
    elif resp_type == 'playlist':
        video_obj = data['video'][0]['video'][0]
    elif resp_type == 'full-playlist':
        video_obj = data['source']
    else:
        raise RuntimeError(f"Невідомий тип відповіді API: {resp_type}")

    media_list = video_obj.get('media', [])
    if not media_list:
        raise RuntimeError(
            "Відео поки що недоступне (можливо, серія ще не вийшла або потрібна підписка)."
        )

    best = _pick_best_media(media_list)
    title = video_obj.get('name') or data.get('name') or ''
    # API може повертати назву з порушеним кодуванням — беремо з HTML сторінки
    if not title or '\ufffd' in title:
        title = _get_page_title(stb_url)

    return {
        'title':    title,
        'duration': video_obj.get('duration', 0),
        'poster':   video_obj.get('poster') or data.get('poster', ''),
        'url':      best['url'],
        'quality':  best.get('quality', '?'),
        'media':    media_list,
    }


async def async_get_episode_info(stb_url: str) -> dict:
    """Асинхронна обгортка для get_episode_info."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_episode_info, stb_url)


# ---------------------------------------------------------------------------
# Пошук серій на сайті STB (МастерШеф)
# Сайт надає список серій у вигляді HTML-сторінки з архівом серій.
# ---------------------------------------------------------------------------

MASTERCHEF_ARCHIVE = "https://www.stb.ua/masterchef/ru/video-2/"

# Matches episode cards: <a class="item-preview-link..." href="EPISODE_URL"><img ... alt="TITLE" ...>
CARD_RE = re.compile(
    r'<a[^>]+href="(https://www\.stb\.ua/masterchef/(?:ru|ua)/episode/[^"]+)"[^>]*>'
    r'\s*<img[^>]+src="([^"]+)"[^>]+alt="([^"]*)"',
    re.DOTALL,
)

def search_episodes(query: str = '', limit: int = 20) -> list[dict]:
    """
    Шукає серії МастерШефа на архівній сторінці STB.
    Повертає список словників: {title, url, poster}.
    query — рядок для фільтрації (пошук по назві), '' = всі.
    """
    html = _fetch(MASTERCHEF_ARCHIVE).decode('utf-8', errors='replace')

    results = []
    seen = set()

    for m in CARD_RE.finditer(html):
        ep_url = m.group(1).strip()
        poster = m.group(2).strip()
        title  = m.group(3).strip()

        if ep_url in seen:
            continue
        seen.add(ep_url)

        # Fallback title from slug if alt is empty
        if not title:
            slug  = ep_url.rstrip('/').split('/')[-1]
            title = slug.replace('-', ' ').title()

        if query and query.lower() not in title.lower():
            continue

        results.append({'title': title, 'url': ep_url, 'poster': poster})

        if len(results) >= limit:
            break

    return results


async def async_search_episodes(query: str = '', limit: int = 20) -> list[dict]:
    """Асинхронна обгортка для search_episodes."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, search_episodes, query, limit)

