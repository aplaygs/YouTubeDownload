"""
Модуль системных интеграций для macOS.

Отвечает за:
1. Отправку нативных всплывающих уведомлений macOS через osascript.
2. Открытие скачанных файлов в Finder (reveal in Finder) и воспроизведение.
3. Безопасную очистку имен файлов от недопустимых символов в файловой системе.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Union


def send_macos_notification(title: str, message: str, subtitle: str = "") -> None:
    """
    Отправляет всплывающее системное уведомление macOS.
    Использует AppleScript через osascript.

    :param title: Заголовок уведомления (например, "YouTubeDownload")
    :param message: Основной текст
    :param subtitle: Подзаголовок (опционально)
    """
    # Экранируем двойные кавычки для AppleScript
    clean_title = title.replace('"', '\\"')
    clean_msg = message.replace('"', '\\"')
    clean_sub = subtitle.replace('"', '\\"')

    if clean_sub:
        script = f'display notification "{clean_msg}" with title "{clean_title}" subtitle "{clean_sub}" sound name "Glass"'
    else:
        script = f'display notification "{clean_msg}" with title "{clean_title}" sound name "Glass"'

    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=3)
    except Exception:
        # Если отправка уведомления не удалась, программа не должна прерываться
        pass


def reveal_in_finder(file_path: Union[str, Path]) -> bool:
    """
    Выделяет скачанный файл в окне Finder (`open -R`).

    :param file_path: Путь к файлу
    :return: True в случае успеха
    """
    path = Path(file_path).resolve()
    if not path.exists():
        # Если файл не существует, пробуем открыть родительскую папку
        parent = path.parent
        if parent.exists():
            subprocess.run(["open", str(parent)])
            return True
        return False

    try:
        subprocess.run(["open", "-R", str(path)], check=True)
        return True
    except Exception:
        return False


def open_file(file_path: Union[str, Path]) -> bool:
    """
    Открывает медиафайл в стандартном проигрывателе macOS (QuickTime Player, IINA, VLC).
    """
    path = Path(file_path).resolve()
    if not path.exists():
        return False
    try:
        subprocess.run(["open", str(path)], check=True)
        return True
    except Exception:
        return False


def sanitize_filename(name: str) -> str:
    """
    Очищает имя файла от запрещенных и опасных символов:
    Заменяет двоеточия, слэши, пайпы и управляющие символы на подчеркивание.
    """
    # Удаляем запрещенные символы для macOS / Linux
    cleaned = re.sub(r'[/\\:*?"<>|\x00-\x1f]', '_', name)
    # Ограничиваем длину имени файла до 200 символов
    if len(cleaned) > 200:
        cleaned = cleaned[:200].rstrip()
    return cleaned.strip()
