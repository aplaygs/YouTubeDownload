"""
Модуль загрузки медиапотоков через yt-dlp и объединения через FFmpeg.

Отвечает за:
1. Загрузку видео в выбранном разрешении (4K, 1080p, 720p и др.) со звуком.
2. Автоматический подбор максимально совместимых с macOS кодеков (H.264/MP4 + AAC/M4A).
3. Извлечение и конвертацию аудио в MP3 (320 kbps) с сохранением обложки и тегов.
4. Многопоточную загрузку фрагментов для максимальной скорости.
5. Потокобезопасные коллбэки прогресса для CLI и GUI.
6. Интеграцию с локальным FFmpeg без необходимости прав суперпользователя.
7. Подключение JS-рантайма (Node.js/JSC) для обхода n-sig троттлинга.
"""

import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Optional
import yt_dlp

from core.config import config
from core.extractor import find_js_runtime


def get_ffmpeg_binary_path() -> Optional[str]:
    """
    Определяет путь к исполняемому файлу ffmpeg:
    1. Проверяет внутри виртуального окружения (venv/bin/ffmpeg).
    2. Проверяет в системном PATH.
    3. Использует static_ffmpeg, если доступен.
    """
    venv_ffmpeg = Path(__file__).resolve().parent.parent / "venv" / "bin" / "ffmpeg"
    if venv_ffmpeg.exists() and os.access(venv_ffmpeg, os.X_OK):
        return str(venv_ffmpeg)

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import static_ffmpeg
        ffmpeg_exe, _ = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
        return ffmpeg_exe
    except Exception:
        pass

    return None


class DownloadManager:
    """
    Класс для управления процессом скачивания медиафайлов.
    """

    def __init__(self, progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        :param progress_callback: Функция обратного вызова для передачи статуса и прогресса
        """
        self.progress_callback = progress_callback
        self.is_cancelled = False
        self.downloaded_file_path: Optional[str] = None

    def _hook(self, d: Dict[str, Any]) -> None:
        """Внутренний перехватчик событий yt-dlp."""
        if self.is_cancelled:
            raise Exception("Загрузка отменена пользователем.")

        if not self.progress_callback:
            return

        status = d.get("status")

        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0

            percent = (downloaded / total * 100) if total > 0 else 0.0

            # Форматирование скорости
            if speed > 1024 * 1024:
                speed_str = f"{speed / (1024 * 1024):.1f} МБ/с"
            elif speed > 1024:
                speed_str = f"{speed / 1024:.1f} КБ/с"
            else:
                speed_str = f"{speed:.0f} Б/с"

            # Форматирование остатка времени
            if eta > 0:
                mins, secs = divmod(int(eta), 60)
                eta_str = f"{mins:02d}:{secs:02d}"
            else:
                eta_str = "--:--"

            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024) if total > 0 else 0.0

            self.progress_callback({
                "status": "downloading",
                "percent": percent,
                "speed_str": speed_str,
                "eta_str": eta_str,
                "downloaded_str": f"{downloaded_mb:.1f} МБ",
                "total_str": f"{total_mb:.1f} МБ",
                "filename": d.get("filename", "")
            })

        elif status == "finished":
            self.downloaded_file_path = d.get("filename")
            self.progress_callback({
                "status": "processing",
                "percent": 100.0,
                "message": "Объединение видео и аудио через FFmpeg..."
            })

    def cancel(self) -> None:
        """Отмена текущей загрузки."""
        self.is_cancelled = True

    def download(
        self,
        url: str,
        resolution: str = "1080p",
        audio_only: bool = False,
        output_dir: Optional[Path] = None
    ) -> str:
        """
        Запускает скачивание ролика или аудио.

        :param url: Ссылка на видео YouTube
        :param resolution: "best", "4k", "1440p", "1080p", "720p", "480p", "360p"
        :param audio_only: Если True, извлекается только звук в MP3
        :param output_dir: Папка для сохранения
        :return: Абсолютный путь к готовому скачанному файлу
        """
        self.is_cancelled = False
        target_dir = output_dir or config.download_path
        target_dir.mkdir(parents=True, exist_ok=True)

        ffmpeg_path = get_ffmpeg_binary_path()

        ydl_opts: Dict[str, Any] = {
            "outtmpl": str(target_dir / "%(title)s [%(resolution)s].%(ext)s"),
            "progress_hooks": [self._hook],
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "retries": config.get("retries", 10),
            "fragment_retries": config.get("fragment_retries", 10),
            "concurrent_fragment_downloads": config.get("concurrent_fragments", 5),
        }

        # Подключение JS runtime для расшифровки подписей на полной скорости
        if config.get("use_js_runtime", True):
            js_runtime = find_js_runtime()
            if js_runtime:
                ydl_opts["js_runtimes"] = js_runtime

        # Указываем путь к папке с FFmpeg
        if ffmpeg_path:
            ydl_opts["ffmpeg_location"] = os.path.dirname(ffmpeg_path)

        # Поддержка прокси
        if config.proxy_url:
            ydl_opts["proxy"] = config.proxy_url

        if audio_only:
            # Режим скачивания только звука (конвертация в MP3 320 kbps)
            ydl_opts["outtmpl"] = str(target_dir / "%(title)s.%(ext)s")
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": config.get("audio_format", "mp3"),
                    "preferredquality": str(config.get("audio_quality", "320")),
                }
            ]
            if config.get("embed_thumbnail", True):
                ydl_opts["writethumbnail"] = True
                ydl_opts["postprocessors"].append({"key": "EmbedThumbnail"})
            if config.get("embed_metadata", True):
                ydl_opts["postprocessors"].append({"key": "FFmpegMetadata"})
        else:
            # Режим скачивания видео со звуком:
            # Отдаем приоритет MP4(H.264)+M4A(AAC) для мгновенной совместимости с QuickTime/macOS,
            # с надежным fallback на любой лучший видео+аудио поток.
            if resolution in ("best", "4k", "2160p"):
                fmt = "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best"
            elif resolution in ("1440p", "2k"):
                fmt = "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best"
            elif resolution == "1080p":
                fmt = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best"
            elif resolution == "720p":
                fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best"
            elif resolution == "480p":
                fmt = "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best"
            elif resolution == "360p":
                fmt = "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best"
            else:
                fmt = f"bestvideo[height<={resolution}]+bestaudio/best"

            ydl_opts["format"] = fmt
            ydl_opts["merge_output_format"] = "mp4"

            if config.get("embed_metadata", True):
                ydl_opts["postprocessors"] = [{"key": "FFmpegMetadata"}]

        # Выполнение загрузки
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if "entries" in info:
                info = next(iter(info["entries"]))
            final_filename = ydl.prepare_filename(info)

            if audio_only:
                ext = config.get("audio_format", "mp3")
                final_filename = os.path.splitext(final_filename)[0] + f".{ext}"
            else:
                final_filename = os.path.splitext(final_filename)[0] + ".mp4"

            self.downloaded_file_path = final_filename

        if self.progress_callback:
            self.progress_callback({
                "status": "finished",
                "percent": 100.0,
                "filename": self.downloaded_file_path
            })

        return self.downloaded_file_path
