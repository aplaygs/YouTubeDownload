"""
Модуль управления конфигурацией YouTubeDownload.

Отвечает за:
1. Загрузку и сохранение настроек из config.json.
2. Хранение путей по умолчанию (папка загрузки ~/Downloads/YouTube).
3. Настройки JS-рантайма (Node.js/JSC) для решения n-sig и получения всех разрешений (1080p/4K).
4. Настройки прокси и многопоточности.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

# Базовая директория проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Путь к файлу конфигурации
CONFIG_FILE = BASE_DIR / "config.json"

# Стандартная папка для сохранения загрузок на macOS
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "YouTube"

# Стандартные настройки по умолчанию
DEFAULT_CONFIG: Dict[str, Any] = {
    # Директория для сохранения загруженных файлов
    "download_dir": str(DEFAULT_DOWNLOAD_DIR),
    # Предпочитаемое качество видео: "best", "4k", "1440p", "1080p", "720p", "480p", "360p"
    "preferred_resolution": "1080p",
    # Формат аудио при выборе загрузки только звука: "mp3", "m4a", "flac", "wav"
    "audio_format": "mp3",
    # Битрейт MP3 в кбит/с (320 - максимальное качество)
    "audio_quality": "320",
    # Использовать ли автоматическое подключение JS Runtime (Node.js / macOS JavaScriptCore)
    # Это разблокирует решение n-sig и отдает полные форматы 1080p/4K со звуком
    "use_js_runtime": True,
    # Резервный список клиентов YouTube на случай блокировки веб-клиента провайдером
    "fallback_player_clients": ["web", "tv", "android", "ios"],
    # Адрес прокси-сервера (если нужен, например: "socks5://127.0.0.1:10808" или "http://127.0.0.1:7890")
    "proxy": "",
    # Количество повторных попыток при сетевых сбоях
    "retries": 10,
    # Количество попыток загрузки отдельных фрагментов
    "fragment_retries": 10,
    # Количество одновременных потоков загрузки фрагментов (ускоряет скачивание)
    "concurrent_fragments": 5,
    # Вшивать ли обложку (thumbnail) в итоговый видео/аудио файл
    "embed_thumbnail": True,
    # Вшивать ли метаданные (название, автор, альбом)
    "embed_metadata": True,
    # Шаблон имени файла: %(title)s - название, %(resolution)s - разрешение, %(ext)s - расширение
    "filename_template": "%(title)s [%(resolution)s].%(ext)s"
}


class Config:
    """
    Класс для работы с конфигурацией приложения.
    Поддерживает автоматическое сохранение изменений на диск.
    """

    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """Загружает настройки из JSON-файла или создает дефолтные, если файла нет."""
        if not self.config_path.exists():
            return dict(DEFAULT_CONFIG)
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                merged = dict(DEFAULT_CONFIG)
                merged.update(loaded)
                return merged
        except Exception as e:
            print(f"[Предупреждение] Ошибка чтения {self.config_path}: {e}. Используются настройки по умолчанию.")
            return dict(DEFAULT_CONFIG)

    def save(self) -> None:
        """Сохраняет текущую конфигурацию в config.json."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[Ошибка] Не удалось сохранить конфигурацию: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Получает значение параметра по ключу."""
        return self._data.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        """Устанавливает значение параметра и опционально сохраняет на диск."""
        self._data[key] = value
        if auto_save:
            self.save()

    @property
    def download_path(self) -> Path:
        """Возвращает валидный объект Path для папки загрузки (создает ее, если нужно)."""
        raw_path = self.get("download_dir", str(DEFAULT_DOWNLOAD_DIR))
        path = Path(os.path.expanduser(raw_path)).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def proxy_url(self) -> str:
        """URL прокси или пустая строка."""
        return str(self.get("proxy", "")).strip()


# Глобальный синглтон конфигурации для удобного доступа
config = Config()
