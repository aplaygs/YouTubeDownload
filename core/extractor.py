"""
Модуль извлечения и анализа информации о видео YouTube.

Отвечает за:
1. Быстрое получение метаданных видео (название, автор, длительность, миниатюра) без скачивания.
2. Анализ доступных разрешений видео (4K, 2K, 1080p, 720p, 480p, 360p) и аудиопотоков.
3. Автоматическое подключение JS runtime (Node.js / macOS JavaScriptCore) для расшифровки подписей n-sig
   и получения полных форматов 1080p/4K со звуком.
4. Каскадный fallback при сбоях сети или блокировках.
"""

import os
import shutil
from typing import Any, Dict, List, Optional
import yt_dlp

from core.config import config


def find_js_runtime() -> Optional[Dict[str, Dict[str, str]]]:
    """
    Автоматически обнаруживает доступный JavaScript runtime (Node.js или встроенный macOS JavaScriptCore).
    Необходим yt-dlp для решения YouTube n-sig челленджа и разблокировки полной скорости и всех форматов.
    """
    node = shutil.which("node")
    if node:
        return {"node": {"path": node}}

    # Встроенный в macOS движок JavaScriptCore
    mac_jsc = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"
    if os.path.exists(mac_jsc) and os.access(mac_jsc, os.X_OK):
        return {"jsc": {"path": mac_jsc}}

    return None


class VideoInfo:
    """Хранилище структурированной информации о видео."""

    def __init__(self, raw_info: Dict[str, Any]):
        self.id: str = raw_info.get("id", "")
        self.title: str = raw_info.get("title", "Без названия")
        self.channel: str = raw_info.get("uploader", raw_info.get("channel", "Неизвестный автор"))
        self.duration: int = raw_info.get("duration", 0)  # секунды
        self.thumbnail: str = raw_info.get("thumbnail", "")
        self.view_count: int = raw_info.get("view_count", 0)
        self.webpage_url: str = raw_info.get("webpage_url", "")
        self.raw: Dict[str, Any] = raw_info

    @property
    def formatted_duration(self) -> str:
        """Форматирует длительность в вид ЧЧ:ММ:СС или ММ:СС."""
        if not self.duration:
            return "Неизвестно"
        hours = self.duration // 3600
        minutes = (self.duration % 3600) // 60
        seconds = self.duration % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def get_quality_options(self) -> List[Dict[str, Any]]:
        """
        Возвращает детальный список доступных качеств для конкретного видео,
        с учетом реального разрешения и частоты кадров (FPS) с YouTube.
        """
        formats = self.raw.get("formats", [])
        height_map: Dict[int, int] = {}
        for f in formats:
            h = f.get("height")
            if f.get("vcodec") != "none" and h:
                h = int(h)
                fps = int(f.get("fps") or 0)
                if h not in height_map or fps > height_map[h]:
                    height_map[h] = fps

        options = []
        for h in sorted(height_map.keys(), reverse=True):
            if h < 240:
                continue  # Пропускаем слишком низкое разрешение 144p
            fps = height_map[h]
            fps_tag = f"{fps}fps " if fps >= 50 else ""
            if h >= 2160:
                label = f"2160p {fps_tag}• 4K Ultra HD"
            elif h >= 1440:
                label = f"1440p {fps_tag}• 2K Quad HD"
            elif h >= 1080:
                label = f"1080p {fps_tag}• Full HD"
            elif h >= 720:
                label = f"720p {fps_tag}• HD"
            elif h >= 480:
                label = f"480p • SD"
            else:
                label = f"{h}p"

            options.append({
                "label": label.strip(),
                "height": h,
                "fps": fps
            })

        return options

    def get_available_resolutions(self) -> List[int]:
        """
        Возвращает отсортированный список доступных разрешений
        (например: [2160, 1440, 1080, 720, 480, 360]).
        """
        options = self.get_quality_options()
        return [opt["height"] for opt in options]


def build_ydl_extract_options(use_clients_override: bool = False) -> Dict[str, Any]:
    """
    Формирует параметры yt-dlp для безопасного и быстрого извлечения информации.
    """
    opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "socket_timeout": 15,
        "retries": config.get("retries", 10),
    }

    # Подключение JS runtime для расшифровки n-sig
    if config.get("use_js_runtime", True):
        js_runtime = find_js_runtime()
        if js_runtime:
            opts["js_runtimes"] = js_runtime

    # Прокси, если указан
    if config.proxy_url:
        opts["proxy"] = config.proxy_url

    # Резервный перебор клиентов, если основной веб-клиент заблокирован
    if use_clients_override:
        clients = config.get("fallback_player_clients", ["tv", "android", "ios"])
        opts["extractor_args"] = {
            "youtube": {
                "player_client": clients,
                "player_skip": ["webpage", "configs"]
            }
        }

    return opts


def extract_video_info(url: str) -> VideoInfo:
    """
    Извлекает информацию о видео по URL.
    1. Пробует основной способ с JS runtime (дает полные 1080p/4K).
    2. При сетевом сбое или 403 пробует резервные клиенты.

    :param url: Ссылка на видео YouTube
    :return: Объект VideoInfo с метаданными и форматами
    :raises RuntimeError: Если не удалось извлечь информацию
    """
    # 1. Основная попытка (стандартный клиент + Node.js/JSCore runtime)
    last_error = None
    try:
        opts = build_ydl_extract_options(use_clients_override=False)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                if "entries" in info:
                    info = next(iter(info["entries"]))
                return VideoInfo(info)
    except Exception as e:
        last_error = e

    # 2. Резервная попытка (альтернативные клиенты tv/android)
    try:
        fallback_opts = build_ydl_extract_options(use_clients_override=True)
        with yt_dlp.YoutubeDL(fallback_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                if "entries" in info:
                    info = next(iter(info["entries"]))
                return VideoInfo(info)
    except Exception as e:
        last_error = e

    raise RuntimeError(
        f"Не удалось получить информацию о видео: {last_error}\n"
        f"Рекомендация: Проверьте интернет-соединение или включите VPN/прокси в настройках."
    )
