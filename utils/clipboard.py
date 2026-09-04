"""
Модуль для безопасной работы с буфером обмена macOS.

Отвечает за:
1. Автоматическое считывание скопированного текста через pyperclip или системный pbpaste.
2. Валидацию ссылок на принадлежность к YouTube (стандартные ролики, shorts, youtu.be).
"""

import re
import subprocess
from typing import Optional

# Регулярное выражение для проверки ссылок YouTube
YOUTUBE_URL_REGEX = re.compile(
    r"^(https?://)?(www\.|m\.)?(youtube\.com/(watch\?.*v=|shorts/|playlist\?|live/)|youtu\.be/)[a-zA-Z0-9_\-\?&=]+",
    re.IGNORECASE
)


def get_clipboard_text() -> str:
    """
    Безопасно извлекает текст из буфера обмена macOS:
    Сначала пробует через системную утилиту pbpaste (нативно и без задержек),
    затем fallback на pyperclip.
    """
    # 1. Попытка через pbpaste (нативно для macOS)
    try:
        proc = subprocess.run(
            ["pbpaste"],
            capture_output=True,
            text=True,
            timeout=1,
            check=True
        )
        return proc.stdout.strip()
    except Exception:
        pass

    # 2. Попытка через pyperclip
    try:
        import pyperclip
        text = pyperclip.paste()
        return (text or "").strip()
    except Exception:
        pass

    return ""


def is_youtube_url(url: str) -> bool:
    """
    Проверяет, является ли строка корректным URL YouTube.
    """
    if not url:
        return False
    url = url.strip()
    return bool(YOUTUBE_URL_REGEX.search(url))


def get_youtube_url_from_clipboard() -> Optional[str]:
    """
    Возвращает URL YouTube из буфера обмена, если он там есть, иначе None.
    """
    text = get_clipboard_text()
    if is_youtube_url(text):
        return text
    return None
